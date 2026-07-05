"""
MCP server exposing the hardened Alpaca execution layer to the trader agents.

This replaces the third-party `alpaca-mcp-server` for the trader. Every order
mutation goes through `alpaca_exec`, which adds idempotency keys, retries with
backoff, and bounded fill polling. Tool names mirror the old server so agent
instructions read naturally, but their behaviour is now hardened.
"""

from mcp.server.fastmcp import FastMCP

import alpaca_exec
from accounts import Account
from symbols import normalize_symbol

mcp = FastMCP("alpaca_exec_server")


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _record_fill(account_name: str, side: str, symbol: str, qty: float, price: float, rationale: str) -> dict:
    """Write a filled order into the trader's SQLite ledger (per-trader attribution).

    Quantities are stored as whole units to match the account model. Returns a
    small status dict; a sell that exceeds the trader's recorded holdings is
    reported (logged.ok=False) rather than raised — reconcile_holdings catches drift.
    """
    units = int(round(qty))
    if units <= 0:
        return {"ok": False, "error": "filled quantity rounded to 0"}
    # Store under the canonical symbol so a buy as "BTC/USD" and a later sell as
    # "BTCUSD" land on the same holding within the trader's ledger.
    symbol = normalize_symbol(symbol)
    try:
        account = Account.get(account_name)
        account.update_holdings_and_transactions(
            "buy" if side.lower() == "buy" else "sell",
            symbol, units, rationale or f"{side} {symbol}", price,
        )
        return {"ok": True, "symbol": symbol, "quantity": units, "price": price}
    except Exception as e:  # noqa: BLE001
        print(f"[exec] auto-log failed for {account_name} {side} {symbol}: {e}")
        return {"ok": False, "error": str(e)}


async def _place_and_log(
    *, asset_class: str, account_name: str | None, rationale: str,
    symbol: str, qty: float, side: str, order_type: str,
    limit_price: float | None, time_in_force: str, client_order_id: str | None,
) -> dict:
    """Submit an order, wait for the fill, and (if account_name given) record it.

    Collapses place -> await fill -> log into a single, guaranteed step so the
    trader can never forget to record a buy/sell. Returns the order result plus
    `fill` (final status) and `logged` (the SQLite write outcome).
    """
    res = await alpaca_exec.submit_order(
        symbol=symbol, qty=qty, side=side, asset_class=asset_class,
        order_type=order_type, limit_price=limit_price,
        time_in_force=time_in_force, client_order_id=client_order_id,
    )
    if not res.get("ok") or not account_name:
        return res

    order_id = res.get("id")
    fill = await alpaca_exec.await_order_fill(order_id) if order_id else {}
    filled_qty = _to_float(fill.get("filled_qty"))
    filled_price = _to_float(fill.get("filled_avg_price"))

    logged = None
    if filled_qty > 0 and filled_price > 0:
        logged = _record_fill(account_name, side, symbol, filled_qty, filled_price, rationale)
    return {**res, "fill": fill, "logged": logged}


@mcp.tool()
async def place_stock_order(
    account_name: str,
    symbol: str,
    qty: float,
    side: str,
    rationale: str = "",
    order_type: str = "market",
    limit_price: float | None = None,
    time_in_force: str = "day",
    client_order_id: str | None = None,
) -> dict:
    """Place a stock order — it executes, waits for the fill, AND records the trade
    to your account automatically. Idempotent and retried.

    Args:
        account_name: Your trader name (e.g. "Warren") — required for logging.
        symbol: Ticker, e.g. "AAPL".
        qty: Number of shares.
        side: "buy" or "sell".
        rationale: Short reason for the trade (stored with the transaction).
        order_type: "market" (default) or "limit".
        limit_price: Required when order_type="limit".
        time_in_force: "day" (default), "gtc", "ioc", etc.
        client_order_id: Optional stable idempotency key.

    Returns `ok` plus the order `id`/`status`, `fill` (final fill info), and
    `logged` (the SQLite recording result; logged.ok=False means the order filled
    but recording it failed). On failure `ok` is False with `error`/`retryable`.
    Do NOT call any separate logging or fill-polling tool — it's handled here.
    """
    return await _place_and_log(
        asset_class="stock", account_name=account_name, rationale=rationale,
        symbol=symbol, qty=qty, side=side, order_type=order_type,
        limit_price=limit_price, time_in_force=time_in_force, client_order_id=client_order_id,
    )


@mcp.tool()
async def place_crypto_order(
    account_name: str,
    symbol: str,
    qty: float,
    side: str,
    rationale: str = "",
    order_type: str = "market",
    limit_price: float | None = None,
    time_in_force: str = "gtc",
    client_order_id: str | None = None,
) -> dict:
    """Place a crypto order (e.g. symbol="BTC/USD"). Executes, waits for the fill,
    and records the trade to your account automatically.

    Crypto uses time_in_force "gtc" by default ("day" is not valid for crypto).
    See place_stock_order for the args and return shape.
    """
    return await _place_and_log(
        asset_class="crypto", account_name=account_name, rationale=rationale,
        symbol=symbol, qty=qty, side=side, order_type=order_type,
        limit_price=limit_price, time_in_force=time_in_force, client_order_id=client_order_id,
    )


@mcp.tool()
async def await_order_fill(order_id: str, timeout_seconds: float = 60.0) -> dict:
    """Wait for an order to fill (or otherwise finish) up to a timeout.

    Use this INSTEAD of calling get_orders in a loop. Returns the order with its
    final `status`, `filled_qty` and `filled_avg_price`. If `timed_out` is True
    the order had not reached a terminal state within `timeout_seconds`.
    """
    return await alpaca_exec.await_order_fill(order_id, timeout_seconds=timeout_seconds)


@mcp.tool()
async def get_orders(status: str = "open") -> list[dict]:
    """List orders. status is "open" (default), "closed" or "all"."""
    return await alpaca_exec.get_orders(status=status)


@mcp.tool()
async def cancel_order(order_id: str) -> dict:
    """Cancel a single order by id."""
    return await alpaca_exec.cancel_order(order_id)


@mcp.tool()
async def cancel_stale_orders() -> dict:
    """Cancel any still-open (new/accepted) orders left from a prior cycle."""
    return await alpaca_exec.cancel_stale_orders()


@mcp.tool()
async def get_account_info() -> dict:
    """Account snapshot: cash, buying_power, equity, portfolio_value, status."""
    return await alpaca_exec.get_account_info()


@mcp.tool()
async def get_positions() -> list[dict]:
    """Current open positions with qty, entry price, market value and P/L."""
    return await alpaca_exec.get_positions()


@mcp.tool()
async def close_position(symbol: str) -> dict:
    """Liquidate the entire position for a symbol (retried, idempotent-safe)."""
    return await alpaca_exec.close_position(symbol)


if __name__ == "__main__":
    mcp.run(transport="stdio")
