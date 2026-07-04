"""Symbol canonicalization shared across the backend.

Kept dependency-free so any module (exec server, reconcile) can import it without
pulling in heavier packages.
"""


def normalize_symbol(symbol: str) -> str:
    """Canonical key for a tradable symbol.

    Crypto pairs differ only by formatting — Alpaca reports "BTCUSD" while the
    agents trade "BTC/USD". Collapsing to an upper-cased, slash-free form makes
    them compare/store consistently. Stock tickers (no slash) are unaffected.
    """
    return symbol.upper().replace("/", "").strip()
