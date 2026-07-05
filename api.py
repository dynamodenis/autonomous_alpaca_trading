"""FastAPI backend for the AI Trading Floor.

Exposes the trading floor's data (accounts, logs) and lifecycle controls
(start/stop) as a REST API for the React frontend. Replaces the old Gradio UI.

Run from the repo root so the cwd-relative paths used by the MCP
servers (`uv run accounts_server.py`, `file:./memory/{name}.db`) resolve:

    uvicorn api:app --host 0.0.0.0 --port 8000
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from accounts import Account
from database import read_log
from floor_control import is_floor_running, start_trading_floor, stop_trading_floor
from reconcile import (
    reconcile_all_blocking,
    sync_balances_from_alpaca,
    sync_balances_from_alpaca_blocking,
)
from trading_floor import lastnames, names, short_model_names
from util import alpaca_get_clock

load_dotenv(override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On server load, sync each trader's balance from the live Alpaca account so
    # the SQLite the frontend reads reflects real money. Non-fatal: a brokerage
    # error just leaves existing balances (and all history) untouched.
    try:
        report = await sync_balances_from_alpaca()
        print(f"[startup] Alpaca balance sync: {report}")
    except Exception as e:  # noqa: BLE001
        print(f"[startup] Alpaca balance sync failed: {e}")
    yield


app = FastAPI(title="AI Trading Floor API", version="1.0.0", lifespan=lifespan)

# CORS — allow the React dev server / deployed frontend origin(s).
# Set FRONTEND_ORIGINS as a comma-separated list; defaults to "*" for local dev.
_origins = os.getenv("FRONTEND_ORIGINS", "*")
allow_origins = ["*"] if _origins.strip() == "*" else [o.strip() for o in _origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Canonical trader metadata (single source of truth: trading_floor lists).
TRADERS = [
    {"name": name, "lastname": lastname, "model": model}
    for name, lastname, model in zip(names, lastnames, short_model_names)
]
_TRADER_BY_LOWER = {t["name"].lower(): t for t in TRADERS}


def _resolve_trader(name: str) -> dict:
    trader = _TRADER_BY_LOWER.get(name.lower())
    if trader is None:
        raise HTTPException(status_code=404, detail=f"Unknown trader: {name}")
    return trader


def _account_payload(name: str) -> dict:
    """Build an account snapshot WITHOUT mutating the time series.

    Unlike `Account.report()`, this does not append a new portfolio-value
    point or save on every read — important since the frontend polls this.
    """
    account = Account.get(name)
    portfolio_value = account.calculate_portfolio_value()
    pnl = account.calculate_profit_loss(portfolio_value)
    return {
        "name": account.name,
        "balance": account.balance,
        "strategy": account.strategy,
        "holdings": account.holdings,
        "transactions": [t.model_dump() for t in account.transactions],
        "portfolio_value_time_series": account.portfolio_value_time_series,
        "total_portfolio_value": portfolio_value,
        "total_profit_loss": pnl,
    }


def _logs_payload(name: str, limit: int) -> list[dict]:
    logs = read_log(name, last_n=limit)
    return [
        {"timestamp": timestamp, "type": type_, "message": message}
        for timestamp, type_, message in logs
    ]


@app.get("/api/traders")
def list_traders() -> list[dict]:
    """Trader roster: name, lastname, and the model each one runs on."""
    return TRADERS


@app.get("/api/traders/{name}")
def get_trader(name: str) -> dict:
    """Full account snapshot for a single trader."""
    trader = _resolve_trader(name)
    return {**trader, "account": _account_payload(trader["name"])}


@app.get("/api/traders/{name}/logs")
def get_trader_logs(name: str, limit: int = 13) -> list[dict]:
    """Most recent log entries for a single trader (oldest -> newest)."""
    trader = _resolve_trader(name)
    return _logs_payload(trader["name"], limit)


@app.get("/api/dashboard")
def get_dashboard(log_limit: int = 13) -> list[dict]:
    """Everything the dashboard needs for all traders in one payload."""
    return [
        {
            **trader,
            "account": _account_payload(trader["name"]),
            "logs": _logs_payload(trader["name"], log_limit),
        }
        for trader in TRADERS
    ]


@app.get("/api/floor/status")
def floor_status() -> dict:
    # Include the market clock so the frontend can pause polling outside
    # trading hours instead of hammering the API around the clock.
    return {"running": is_floor_running(), "market": _market_info()}


def _safe_sync() -> dict | None:
    """Sync balances from Alpaca, swallowing errors (never block start/stop)."""
    try:
        return sync_balances_from_alpaca_blocking()
    except Exception as e:  # noqa: BLE001
        print(f"[floor] Alpaca balance sync failed: {e}")
        return {"ok": False, "error": str(e)}


def _market_info() -> dict:
    """Current Alpaca market clock for the UI: is it open, and next open/close."""
    try:
        clock = alpaca_get_clock()
        return {
            "ok": True,
            "is_open": bool(clock.is_open),
            "next_open": clock.next_open.isoformat() if clock.next_open else None,
            "next_close": clock.next_close.isoformat() if clock.next_close else None,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@app.post("/api/floor/start")
def floor_start() -> dict:
    # Sync to the live Alpaca balance before kicking off a trading session.
    sync = _safe_sync()
    message = start_trading_floor()
    market = _market_info()
    # Tell the user whether the first cycle runs now or waits for the open.
    if market.get("ok"):
        message += (
            " Market is open — running the first cycle now."
            if market["is_open"]
            else " Market is closed — no orders/research until the next open."
        )
    return {"running": is_floor_running(), "message": message, "balance_sync": sync, "market": market}


@app.post("/api/floor/stop")
def floor_stop() -> dict:
    message = stop_trading_floor()
    # Sync once more after stopping so the dashboard shows the end-of-session balance.
    sync = _safe_sync()
    return {"running": is_floor_running(), "message": message, "balance_sync": sync}


@app.post("/api/reconcile")
def reconcile_balances() -> dict:
    """Manually reconcile against Alpaca: sync balances + report holdings drift."""
    try:
        return reconcile_all_blocking()
    except Exception as e:  # noqa: BLE001
        print(f"[reconcile] failed: {e}")
        return {"ok": False, "error": str(e)}
