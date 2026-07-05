"""
Hardened Alpaca order-execution layer.

This module owns every call that mutates the brokerage account (order
submission, cancellation, position close) and wraps them with:

  * Idempotency  - every order carries a stable `client_order_id`. The same id
                   is reused across internal retries, so a network blip that
                   hides a successful submission can never produce a duplicate
                   order: Alpaca rejects the retry as a duplicate and we resolve
                   the order that already exists.
  * Retries      - transient failures (429 / 5xx / connection errors) are
                   retried with exponential backoff + jitter. Validation errors
                   (e.g. insufficient buying power) are NOT retried.
  * Bounded fill - `await_order_fill` polls with a hard timeout instead of the
                   previous "let the LLM loop forever" approach.

It is consumed by `alpaca_exec_server.py` (the MCP server the trader agents
talk to). Keeping the logic here, separate from the MCP plumbing, keeps it
unit-testable without spawning a server.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.common.exceptions import APIError

load_dotenv(override=True)

# --- Configuration -----------------------------------------------------------

MAX_RETRIES = int(os.getenv("ALPACA_MAX_RETRIES", "4"))
BACKOFF_BASE_SECONDS = float(os.getenv("ALPACA_BACKOFF_BASE_SECONDS", "0.5"))
BACKOFF_MAX_SECONDS = float(os.getenv("ALPACA_BACKOFF_MAX_SECONDS", "8"))

# HTTP status codes that are safe to retry (transient server / throttling).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Order states that mean "this order is done; stop polling".
TERMINAL_STATUSES = {"filled", "canceled", "cancelled", "rejected", "expired"}

client = TradingClient(
    api_key=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_SECRET_KEY"),
    paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
)


# --- Error classification ----------------------------------------------------


def _error_message(exc: Exception) -> str:
    """Safely extract a human-readable message.

    alpaca-py's `APIError.message` parses the error body as JSON and will raise
    if the body isn't JSON, so we guard the access and fall back to str(exc).
    """
    try:
        msg = getattr(exc, "message", None)
        if msg:
            return str(msg)
    except Exception:  # noqa: BLE001 - property parsing can throw; never propagate
        pass
    return str(exc)


def _is_retryable(exc: Exception) -> bool:
    """Transient errors worth retrying; validation errors are not."""
    if isinstance(exc, APIError):
        return getattr(exc, "status_code", None) in RETRYABLE_STATUS
    # Connection resets, read timeouts, DNS hiccups, etc.
    return isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError, OSError))


def _is_duplicate_order(exc: Exception) -> bool:
    """True when Alpaca rejects an order because the client_order_id already exists.

    This is the signal that a *previous* attempt actually went through — i.e. our
    idempotency key did its job — so the caller should resolve the existing order
    rather than treat it as a failure.
    """
    if not isinstance(exc, APIError):
        return False
    msg = _error_message(exc).lower()
    return "client_order_id" in msg and ("unique" in msg or "exist" in msg or "duplicate" in msg)


# --- Retry wrapper -----------------------------------------------------------


async def _with_retries(label: str, fn, *args, **kwargs):
    """Run a blocking alpaca-py call in a thread with bounded exponential backoff.

    `Math.random`-style jitter is fine here (plain Python process), and avoids a
    thundering herd when several traders retry against the same throttle window.
    """
    import random

    attempt = 0
    while True:
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - we re-raise non-retryable below
            attempt += 1
            if attempt > MAX_RETRIES or not _is_retryable(exc):
                raise
            delay = min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)
            delay += random.uniform(0, delay / 2)  # jitter
            print(f"[alpaca_exec] {label} failed ({exc}); retry {attempt}/{MAX_RETRIES} in {delay:.2f}s")
            await asyncio.sleep(delay)


# --- Serialization -----------------------------------------------------------


def _order_to_dict(order) -> dict:
    """Project an alpaca-py Order into the small, JSON-safe shape agents need."""
    def g(attr):
        val = getattr(order, attr, None)
        return str(val) if val is not None else None

    return {
        "id": g("id"),
        "client_order_id": g("client_order_id"),
        "symbol": g("symbol"),
        "side": g("side"),
        "type": g("order_type") or g("type"),
        "qty": g("qty"),
        "filled_qty": g("filled_qty"),
        "filled_avg_price": g("filled_avg_price"),
        "limit_price": g("limit_price"),
        "time_in_force": g("time_in_force"),
        "status": g("status"),
        "submitted_at": g("submitted_at"),
    }


# --- Public execution API ----------------------------------------------------


async def submit_order(
    symbol: str,
    qty: float,
    side: str,
    asset_class: str = "stock",
    order_type: str = "market",
    limit_price: float | None = None,
    time_in_force: str | None = None,
    client_order_id: str | None = None,
) -> dict:
    """Idempotently submit an order with retries.

    Returns a dict with `ok` plus the order fields. If `ok` is False, `error`
    explains why and `retryable` indicates whether a later attempt might work.
    """
    side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

    # Crypto cannot use DAY; default it to GTC. Stocks default to DAY.
    if time_in_force:
        tif = TimeInForce(time_in_force.lower())
    elif asset_class.lower() == "crypto":
        tif = TimeInForce.GTC
    else:
        tif = TimeInForce.DAY

    # The idempotency key. Reused verbatim across every retry below so a hidden
    # success cannot become a duplicate order. Callers may pass their own stable
    # key to dedupe across separate tool calls.
    coid = client_order_id or f"agent-{uuid.uuid4().hex[:24]}"

    if order_type.lower() == "limit":
        if limit_price is None:
            return {"ok": False, "retryable": False, "error": "limit order requires limit_price"}
        req = LimitOrderRequest(
            symbol=symbol, qty=qty, side=side_enum, time_in_force=tif,
            limit_price=limit_price, client_order_id=coid,
        )
    else:
        req = MarketOrderRequest(
            symbol=symbol, qty=qty, side=side_enum, time_in_force=tif,
            client_order_id=coid,
        )

    try:
        order = await _with_retries(f"submit_order {symbol}", client.submit_order, order_data=req)
        return {"ok": True, **_order_to_dict(order)}
    except APIError as exc:
        if _is_duplicate_order(exc):
            # A prior attempt already landed — resolve and return it. This is the
            # idempotency guarantee paying off, so it is a success, not an error.
            print(f"[alpaca_exec] duplicate client_order_id {coid}; resolving existing order")
            try:
                existing = await _with_retries("get_order_by_client_id", client.get_order_by_client_id, coid)
                return {"ok": True, "idempotent_resolved": True, **_order_to_dict(existing)}
            except Exception as inner:  # noqa: BLE001
                return {"ok": False, "retryable": True, "client_order_id": coid,
                        "error": f"duplicate order but failed to resolve it: {inner}"}
        return {"ok": False, "retryable": _is_retryable(exc), "client_order_id": coid,
                "error": _error_message(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "retryable": _is_retryable(exc), "client_order_id": coid, "error": str(exc)}


async def await_order_fill(order_id: str, timeout_seconds: float = 60.0, poll_interval: float = 2.0) -> dict:
    """Poll an order until it reaches a terminal state or the timeout elapses.

    Replaces the old "call get_orders() repeatedly until filled" agent loop with
    a bounded, server-side poll so a never-filling order can't hang a trade cycle.
    """
    waited = 0.0
    last = None
    while waited <= timeout_seconds:
        try:
            order = await _with_retries("get_order_by_id", client.get_order_by_id, order_id)
            last = _order_to_dict(order)
            if (last.get("status") or "").lower() in TERMINAL_STATUSES:
                return {"ok": True, "done": True, **last}
        except Exception as exc:  # noqa: BLE001
            last = {"error": str(exc)}
        await asyncio.sleep(poll_interval)
        waited += poll_interval
    return {"ok": True, "done": False, "timed_out": True, **(last or {})}


async def cancel_order(order_id: str) -> dict:
    try:
        await _with_retries("cancel_order_by_id", client.cancel_order_by_id, order_id)
        return {"ok": True, "order_id": order_id, "status": "cancel_requested"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "retryable": _is_retryable(exc), "error": str(exc)}


async def cancel_stale_orders() -> dict:
    """Cancel still-open orders left from a previous cycle (status new/accepted)."""
    try:
        orders = await _with_retries(
            "get_orders", client.get_orders, filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "retryable": _is_retryable(exc), "error": str(exc)}

    cancelled = []
    for o in orders:
        if (getattr(o, "status", None) and str(o.status).lower().endswith(("new", "accepted"))):
            res = await cancel_order(str(o.id))
            if res.get("ok"):
                cancelled.append(str(o.id))
    return {"ok": True, "cancelled_count": len(cancelled), "cancelled_ids": cancelled}


async def get_orders(status: str = "open") -> list[dict]:
    req = GetOrdersRequest(status=QueryOrderStatus(status.lower()))
    orders = await _with_retries("get_orders", client.get_orders, filter=req)
    return [_order_to_dict(o) for o in orders]


async def get_account_info() -> dict:
    acct = await _with_retries("get_account", client.get_account)
    return {
        "status": str(getattr(acct, "status", None)),
        "cash": str(getattr(acct, "cash", None)),
        "buying_power": str(getattr(acct, "buying_power", None)),
        "equity": str(getattr(acct, "equity", None)),
        "portfolio_value": str(getattr(acct, "portfolio_value", None)),
        "currency": str(getattr(acct, "currency", None)),
    }


async def get_positions() -> list[dict]:
    positions = await _with_retries("get_all_positions", client.get_all_positions)
    return [
        {
            "symbol": str(getattr(p, "symbol", None)),
            "qty": str(getattr(p, "qty", None)),
            "avg_entry_price": str(getattr(p, "avg_entry_price", None)),
            "market_value": str(getattr(p, "market_value", None)),
            "unrealized_pl": str(getattr(p, "unrealized_pl", None)),
            "side": str(getattr(p, "side", None)),
        }
        for p in positions
    ]


async def close_position(symbol: str) -> dict:
    try:
        order = await _with_retries("close_position", client.close_position, symbol)
        return {"ok": True, **_order_to_dict(order)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "retryable": _is_retryable(exc), "error": str(exc)}
