"""
MCP server exposing the hardened Alpaca execution layer to the trader agents.

This replaces the third-party `alpaca-mcp-server` for the trader. Every order
mutation goes through `alpaca_exec`, which adds idempotency keys, retries with
backoff, and bounded fill polling. Tool names mirror the old server so agent
instructions read naturally, but their behaviour is now hardened.
"""

from mcp.server.fastmcp import FastMCP

import alpaca_exec
import jev
from accounts import Account
from funding import funding_mode
from pending_fills import record_fill, track_pending
from symbols import normalize_symbol

mcp = FastMCP("alpaca_exec_server")


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _size_label(qty: float | None, notional: float | None) -> str:
    return f"${notional:,.2f} of" if notional is not None else f"{qty:g}"


async def _jev_gate(
    *, account_name: str, account: dict, asset_class: str, symbol: str, qty: float | None,
    notional: float | None, side: str, order_type: str, limit_price: float | None, rationale: str,
) -> dict:
    """Have JEV approve or reject the proposed order, and log the verdict."""
    try:
        strategy = Account.get(account_name).strategy
    except Exception:  # noqa: BLE001
        strategy = None
    try:
        canonical = normalize_symbol(symbol)
        position = next(
            (p for p in await alpaca_exec.get_positions() if normalize_symbol(p["symbol"]) == canonical),
            None,
        )
    except Exception as e:  # noqa: BLE001
        position = {"error": str(e)}

    verdict = await jev.judge_order({
        "trader": account_name,
        "strategy": strategy,
        "proposed_order": {
            "side": side, "symbol": symbol, "qty": qty, "notional_usd": notional,
            "asset_class": asset_class,
            "order_type": order_type, "limit_price": limit_price,
        },
        "rationale": rationale or "(none given)",
        "account": account,
        "funding_mode": (
            funding_mode(_to_float(account.get("cash")), _to_float(account.get("equity")))
            if "cash" in account else "UNKNOWN"
        ),
        "current_position": position,
    })
    decision = "APPROVED" if verdict["approved"] else "REJECTED"
    Account.write_log(account_name, "jev", f"{decision} {side.upper()} {_size_label(qty, notional)} {symbol}: {verdict['reason']}")
    return verdict


async def _place_and_log(
    *, asset_class: str, account_name: str | None, rationale: str,
    symbol: str, qty: float | None, side: str, order_type: str,
    limit_price: float | None, time_in_force: str, client_order_id: str | None,
    notional: float | None = None,
) -> dict:
    """Submit an order, wait for the fill, and (if account_name given) record it.

    Collapses place -> await fill -> log into a single, guaranteed step so the
    trader can never forget to record a buy/sell. Returns the order result plus
    `fill` (final status) and `logged` (the SQLite write outcome). When JEV is
    enabled, the order is only submitted if JEV approves it.
    """
    try:
        account = await alpaca_exec.get_account_info()
    except Exception as e:  # noqa: BLE001
        account = {"error": str(e)}

    # Hard rule, independent of the model and JEV: never buy while the shared
    # account's cash is negative (i.e. already borrowing on margin).
    if side.lower() == "buy" and "cash" in account and _to_float(account["cash"]) < 0:
        if account_name:
            Account.write_log(account_name, "jev", f"BLOCKED BUY {_size_label(qty, notional)} {symbol}: cash is negative")
        return {
            "ok": False, "retryable": False, "rejected_by": "funding",
            "error": f"Buy blocked: the account's cash is negative (${_to_float(account['cash']):,.2f}). "
                     "Sell positions to raise cash first; do not retry buys this cycle.",
        }

    verdict = None
    if jev.JEV_ENABLED and account_name:
        verdict = await _jev_gate(
            account_name=account_name, account=account, asset_class=asset_class, symbol=symbol,
            qty=qty, notional=notional, side=side, order_type=order_type, limit_price=limit_price,
            rationale=rationale,
        )
        if not verdict["approved"]:
            return {
                "ok": False, "retryable": False, "rejected_by": "jev", "jev": verdict,
                "error": f"Order rejected by the JEV decision gate: {verdict['reason']}. "
                         "Do not resubmit this order.",
            }

    res = await alpaca_exec.submit_order(
        symbol=symbol, qty=qty, side=side, asset_class=asset_class,
        order_type=order_type, limit_price=limit_price,
        time_in_force=time_in_force, client_order_id=client_order_id, notional=notional,
    )
    if verdict:
        res["jev"] = verdict
    if not res.get("ok") or not account_name:
        return res

    order_id = res.get("id")
    fill = await alpaca_exec.await_order_fill(order_id) if order_id else {}
    filled_qty = _to_float(fill.get("filled_qty"))
    filled_price = _to_float(fill.get("filled_avg_price"))

    logged = None
    if filled_qty > 0 and filled_price > 0:
        logged = record_fill(account_name, side, symbol, filled_qty, filled_price, rationale)

    # Still open (or only partly filled) when the wait gave up: remember it so
    # the fill is recorded later instead of being lost (see pending_fills.py).
    if order_id and not fill.get("done"):
        recorded = filled_qty if logged and logged.get("ok") else 0.0
        if track_pending(order_id, account_name, side, symbol, rationale, recorded, recorded * filled_price):
            fill["note"] = ("Order is still open at the broker. If it fills later it will be recorded "
                            "to your account automatically. Do not wait on it again and do not "
                            "resubmit it; cancel it with cancel_order if it is no longer wanted.")
    return {**res, "fill": fill, "logged": logged}


@mcp.tool()
async def place_stock_order(
    account_name: str,
    symbol: str,
    side: str,
    qty: float | None = None,
    notional: float | None = None,
    rationale: str = "",
    order_type: str = "market",
    limit_price: float | None = None,
    time_in_force: str = "day",
    client_order_id: str | None = None,
) -> dict:
    """Place a stock order — it executes, waits for the fill, AND records the trade
    to your account automatically. Idempotent and retried. Fractional shares are
    supported.

    Size the order with EXACTLY ONE of:
        notional: dollar amount, e.g. 150 buys $150 worth (market orders only).
                  Preferred for buys — it can't overshoot your budget.
        qty:      number of shares, fractions allowed (e.g. 0.35).

    Args:
        account_name: Your trader name (e.g. "Warren") — required for logging.
        symbol: Ticker, e.g. "AAPL".
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
        notional=notional,
    )


@mcp.tool()
async def place_crypto_order(
    account_name: str,
    symbol: str,
    side: str,
    qty: float | None = None,
    notional: float | None = None,
    rationale: str = "",
    order_type: str = "market",
    limit_price: float | None = None,
    time_in_force: str = "gtc",
    client_order_id: str | None = None,
) -> dict:
    """Place a crypto order (e.g. symbol="BTC/USD"). Executes, waits for the fill,
    and records the trade to your account automatically.

    Size with exactly one of `notional` (dollars) or `qty` (units, fractions allowed).
    Crypto uses time_in_force "gtc" by default ("day" is not valid for crypto).
    See place_stock_order for the args and return shape.
    """
    return await _place_and_log(
        asset_class="crypto", account_name=account_name, rationale=rationale,
        symbol=symbol, qty=qty, side=side, order_type=order_type,
        limit_price=limit_price, time_in_force=time_in_force, client_order_id=client_order_id,
        notional=notional,
    )


@mcp.tool()
async def await_order_fill(order_id: str, timeout_seconds: float = 30.0) -> dict:
    """Check on an order, waiting briefly for it to fill (or otherwise finish).

    place_stock_order / place_crypto_order already wait for the fill, so you
    rarely need this. `timeout_seconds` is capped at 45. Returns the order with
    its `status`, `filled_qty` and `filled_avg_price`. If `timed_out` is True the
    order is still open at the broker: do NOT call this again for it this cycle.
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
