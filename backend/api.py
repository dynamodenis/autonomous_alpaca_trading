"""FastAPI backend for the AI Trading Floor.

Exposes the trading floor's data (accounts, logs) and lifecycle controls
(start/stop) as a REST API for the React frontend. Replaces the old Gradio UI.

Run from the `backend/` directory so the cwd-relative paths used by the MCP
servers (`uv run accounts_server.py`, `file:./memory/{name}.db`) resolve:

    uvicorn api:app --host 0.0.0.0 --port 8000
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from accounts import Account
from database import read_log
from floor_control import is_floor_running, start_trading_floor, stop_trading_floor
from trading_floor import lastnames, names, short_model_names

load_dotenv(override=True)

app = FastAPI(title="AI Trading Floor API", version="1.0.0")

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
    return {"running": is_floor_running()}


@app.post("/api/floor/start")
def floor_start() -> dict:
    message = start_trading_floor()
    return {"running": is_floor_running(), "message": message}


@app.post("/api/floor/stop")
def floor_stop() -> dict:
    message = stop_trading_floor()
    return {"running": is_floor_running(), "message": message}
