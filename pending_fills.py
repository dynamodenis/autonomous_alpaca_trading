"""
Ledger recording for fills, including the ones that arrive late.

A trader's ledger is normally written inside place_*_order, right after the
bounded fill wait. An order still open when that wait gives up (a limit order,
an order queued while the market is closed, a partial fill) would otherwise
never be recorded. Such orders are saved as "pending" here, and
`settle_pending_orders` — run by the trading floor before each trader's turn —
looks them up at Alpaca and records whatever has filled since.
"""

import os
import time

import alpaca_exec
import database
from accounts import Account
from symbols import normalize_symbol

# Stop tracking an order this long after it was placed, whatever its state, so
# an order that can never be resolved doesn't get looked up forever.
MAX_AGE_SECONDS = float(os.getenv("PENDING_ORDER_MAX_AGE_DAYS", "7")) * 86400

_EPS = 1e-9


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def record_fill(account_name: str, side: str, symbol: str, qty: float, price: float, rationale: str) -> dict:
    """Write a filled order into the trader's ledger (per-trader attribution).

    Fractional quantities are kept (rounded to 9 decimals, Alpaca's precision).
    Returns a small status dict; errors are reported (ok=False) rather than raised.
    """
    units = round(qty, 9)
    if units <= 0:
        return {"ok": False, "error": "filled quantity is 0"}
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
        print(f"[fills] ledger write failed for {account_name} {side} {symbol}: {e}")
        return {"ok": False, "error": str(e)}


def track_pending(
    order_id: str, account_name: str, side: str, symbol: str, rationale: str,
    recorded_qty: float = 0.0, recorded_value: float = 0.0,
) -> bool:
    """Remember a still-open order so a later fill gets recorded.

    `recorded_qty` / `recorded_value` (qty x price) are what the ledger already
    holds for this order, so a partial fill is never counted twice.
    """
    try:
        database.write_pending_order(order_id, account_name, side, symbol, rationale, recorded_qty, recorded_value)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[fills] could not track pending order {order_id} for {account_name}: {e}")
        return False


async def _settle_one(p: dict) -> str:
    """Bring one pending order up to date. Returns "recorded", "closed" or "open"."""
    order_id, name = p["order_id"], p["name"]
    expired = time.time() - p["created"] > MAX_AGE_SECONDS
    try:
        order = alpaca_exec._order_to_dict(
            await alpaca_exec._with_retries("get_order_by_id", alpaca_exec.client.get_order_by_id, order_id)
        )
    except Exception as e:  # noqa: BLE001
        # Any failure is retried next time, unless Alpaca says the order doesn't
        # exist (404) or we've chased it for too long.
        if expired or getattr(e, "status_code", None) == 404:
            print(f"[fills] dropping pending order {order_id} for {name}: {alpaca_exec._error_message(e)}")
            database.delete_pending_order(order_id)
            return "closed"
        return "open"

    outcome = "open"
    filled_qty = _to_float(order.get("filled_qty"))
    new_qty = filled_qty - p["recorded_qty"]
    if new_qty > _EPS:
        # filled_avg_price averages the whole order; price the new part so that
        # everything recorded for this order adds up to its true total.
        total_value = filled_qty * _to_float(order.get("filled_avg_price"))
        price = (total_value - p["recorded_value"]) / new_qty
        if price > 0:
            logged = record_fill(name, p["side"], p["symbol"], new_qty, price, p["rationale"])
            if not logged.get("ok"):
                return "open"  # leave it untouched; retried on the next pass
            database.update_pending_order(order_id, filled_qty, total_value)
            Account.write_log(
                name, "account",
                f"Late fill recorded: {p['side']} {logged['quantity']:g} {logged['symbol']} at ${price:,.2f}",
            )
            outcome = "recorded"

    status = (order.get("status") or "").lower()
    if status in alpaca_exec.TERMINAL_STATUSES or expired:
        database.delete_pending_order(order_id)
        if outcome == "open":
            outcome = "closed"
    return outcome


async def settle_pending_orders() -> dict:
    """Record fills that arrived after their trader stopped waiting.

    Safe to call often: with nothing pending it is a single DB read. Never
    raises — one bad order must not block a trade cycle.
    """
    counts = {"recorded": 0, "closed": 0, "open": 0}
    try:
        pending = database.read_pending_orders()
    except Exception as e:  # noqa: BLE001
        print(f"[fills] could not read pending orders: {e}")
        return counts
    for p in pending:
        try:
            counts[await _settle_one(p)] += 1
        except Exception as e:  # noqa: BLE001
            print(f"[fills] settling order {p.get('order_id')} failed: {e}")
            counts["open"] += 1
    if pending:
        print(f"[fills] pending orders: {counts}")
    return counts
