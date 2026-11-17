"""Live prices for held symbols, read off the shared Alpaca account's positions.

Every symbol a trader's ledger holds is (normally) an open position on the one
Alpaca account they all trade, and each position carries its current price. So
a single positions call prices every ledger without a market-data plan — unlike
market.get_share_price, which on the free plan only knows yesterday's close.
"""

import os
import threading
import time

from symbols import normalize_symbol

# Reuse a fetched price map for this long: the dashboard polls every few
# seconds and builds four trader payloads per poll.
TTL_SECONDS = float(os.getenv("LIVE_PRICE_TTL_SECONDS", "15"))
# If Alpaca can't be reached, prices this recent are still better than none.
STALE_OK_SECONDS = 600.0

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "prices": None}


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def live_prices(max_age: float = TTL_SECONDS) -> dict[str, float] | None:
    """Current price per normalized symbol for every open Alpaca position.

    Blocking (one HTTP call, bounded by alpaca_exec's HTTP timeout); call it via
    asyncio.to_thread from async code that must not stall. Returns None when
    Alpaca is unreachable and nothing recent is cached — callers should then
    skip recording rather than record a made-up value.
    """
    with _lock:
        age = time.monotonic() - _cache["at"]
        if _cache["prices"] is not None and age <= max_age:
            return _cache["prices"]
        try:
            import alpaca_exec  # lazy: building its client needs the Alpaca keys

            positions = alpaca_exec.client.get_all_positions()
        except Exception as e:  # noqa: BLE001
            print(f"[prices] could not read Alpaca positions: {e}")
            if _cache["prices"] is not None and age <= STALE_OK_SECONDS:
                return _cache["prices"]
            return None

        prices: dict[str, float] = {}
        for p in positions:
            symbol = getattr(p, "symbol", None)
            price = _to_float(getattr(p, "current_price", None))
            if price <= 0:
                qty = _to_float(getattr(p, "qty", None))
                price = _to_float(getattr(p, "market_value", None)) / qty if qty else 0.0
            if symbol and price > 0:
                prices[normalize_symbol(str(symbol))] = abs(price)
        _cache["at"], _cache["prices"] = time.monotonic(), prices
        return prices
