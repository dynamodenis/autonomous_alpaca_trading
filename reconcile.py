"""
Reconcile the local SQLite books against the real Alpaca account.

The four traders (Warren, George, Ray, Cathie) each keep their own simulated
portfolio in SQLite, but they all place real orders against a SINGLE shared
Alpaca account. This module pulls the live Alpaca account value and syncs it
into each trader's `balance` so the frontend (which reads SQLite) reflects the
real money.

Design choices (per product intent):
  * SYNC, don't reseed - we update `balance` only. Holdings, transactions and
    the portfolio-value time series are left untouched, so trading history is
    never lost on a restart or a start/stop.
  * Total account value - the seed/sync figure is the Alpaca account's
    `portfolio_value` (cash + open positions) by default. Override with the
    ALPACA_SEED_FIELD env var (e.g. "cash", "equity").
  * Fail safe - if Alpaca can't be reached, balances are left exactly as they
    are; we never zero them out on a transient error.

Run points: FastAPI startup, and the floor start/stop endpoints (see api.py).
"""

import asyncio
import os

import accounts
from accounts import Account
import alpaca_exec
from symbols import normalize_symbol
from trading_floor import names

# Which Alpaca account figure becomes each trader's balance.
SEED_FIELD = os.getenv("ALPACA_SEED_FIELD", "portfolio_value")


async def fetch_alpaca_balance() -> float | None:
    """Return the configured Alpaca account figure, or None if unavailable."""
    try:
        info = await alpaca_exec.get_account_info()
    except Exception as exc:  # noqa: BLE001 - never let a brokerage hiccup break startup
        print(f"[reconcile] Could not fetch Alpaca account: {exc}")
        return None

    raw = info.get(SEED_FIELD)
    if raw is None:
        print(f"[reconcile] Alpaca account has no '{SEED_FIELD}' field")
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        print(f"[reconcile] Alpaca account has no usable '{SEED_FIELD}' (got {raw!r})")
        return None
    # Guard against NaN.
    if value != value:  # noqa: PLR0124
        return None
    return value


async def sync_balances_from_alpaca() -> dict:
    """Sync every trader's cash balance to the live Alpaca account value.

    Preserves holdings, transactions and time series. Returns a report dict
    describing what changed (used as the API response / log payload).
    """
    balance = await fetch_alpaca_balance()
    report = {
        "ok": balance is not None,
        "field": SEED_FIELD,
        "alpaca_balance": balance,
        "synced": [],
    }

    if balance is None:
        print("[reconcile] Leaving SQLite balances unchanged (no Alpaca value).")
        return report

    # New accounts created from here on seed at the real balance too.
    accounts.set_initial_balance(balance)

    for name in names:
        account = Account.get(name)  # creates the account on first ever run
        old = account.balance
        if old != balance:
            account.balance = balance
            account.save()
            Account.write_log(
                name, "account",
                f"Synced balance from Alpaca {SEED_FIELD}: {old:,.2f} -> {balance:,.2f}",
            )
        report["synced"].append({"name": name, "old_balance": old, "new_balance": balance})

    changed = sum(1 for s in report["synced"] if s["old_balance"] != s["new_balance"])
    print(f"[reconcile] Synced {len(names)} traders to Alpaca {SEED_FIELD}={balance:,.2f} "
          f"({changed} changed).")
    return report


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def reconcile_holdings() -> dict:
    """Compare summed per-trader SQLite holdings against the real Alpaca positions.

    The four traders share one account, so the SUM of their SQLite holdings should
    equal the Alpaca position for each symbol. Symbols are normalized first (so
    "BTC/USD" and "BTCUSD" match). Read-only — reports per-symbol drift, mutates
    nothing.
    """
    try:
        positions = await alpaca_exec.get_positions()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}

    alpaca_qty: dict[str, float] = {}
    for p in positions:
        sym = p.get("symbol")
        if sym:
            key = normalize_symbol(sym)
            alpaca_qty[key] = alpaca_qty.get(key, 0.0) + _to_float(p.get("qty"))

    sqlite_qty: dict[str, float] = {}
    for name in names:
        for sym, q in Account.get(name).holdings.items():
            key = normalize_symbol(sym)
            sqlite_qty[key] = sqlite_qty.get(key, 0.0) + float(q)

    symbols = set(alpaca_qty) | set(sqlite_qty)
    drift = []
    for sym in sorted(symbols):
        a, s = alpaca_qty.get(sym, 0.0), sqlite_qty.get(sym, 0.0)
        if abs(a - s) > 1e-6:
            drift.append({"symbol": sym, "sqlite_total": s, "alpaca_qty": a, "diff": round(s - a, 6)})
            print(f"[reconcile][DRIFT] {sym}: sqlite={s} alpaca={a} diff={round(s - a, 6)}")

    print(f"[reconcile] Holdings check: {len(symbols)} symbols, {len(drift)} drifting.")
    return {"ok": True, "symbols_checked": len(symbols), "drift": drift}


async def reconcile_all() -> dict:
    """Full reconcile: sync balances AND report holdings drift vs Alpaca."""
    balances = await sync_balances_from_alpaca()
    holdings = await reconcile_holdings()
    return {
        "ok": bool(balances.get("ok") and holdings.get("ok")),
        "balances": balances,
        "holdings": holdings,
    }


async def fetch_portfolio_snapshot() -> dict:
    """Live view of the single shared Alpaca account: equity, cash, positions.

    The four traders all trade against this one account, so this snapshot —
    not a sum over traders — is the true combined portfolio.
    """
    try:
        info = await alpaca_exec.get_account_info()
        positions = await alpaca_exec.get_positions()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    try:
        equity = float(info.get("equity"))
        cash = float(info.get("cash"))
    except (TypeError, ValueError):
        return {"ok": False, "error": f"unusable Alpaca account figures: {info!r}"}

    positions_value = 0.0
    for p in positions:
        try:
            positions_value += float(p.get("market_value") or 0.0)
        except (TypeError, ValueError):
            pass

    return {
        "ok": True,
        "equity": equity,
        "cash": cash,
        "positions_value": positions_value,
        "positions_count": len(positions),
    }


def fetch_portfolio_snapshot_blocking() -> dict:
    """Sync wrapper for FastAPI's threadpool-run sync endpoints."""
    return asyncio.run(fetch_portfolio_snapshot())


def sync_balances_from_alpaca_blocking() -> dict:
    """Synchronous wrapper for use from FastAPI's threadpool (sync endpoints)."""
    return asyncio.run(sync_balances_from_alpaca())


def reconcile_all_blocking() -> dict:
    """Synchronous wrapper for the full reconcile (balances + holdings drift)."""
    return asyncio.run(reconcile_all())
