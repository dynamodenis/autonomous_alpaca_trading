from enum import Enum
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import OrderStatus

import threading
import os
from dotenv import load_dotenv
load_dotenv(override=True)

stop_event = threading.Event()

css = """
.positive-pnl {
    color: green !important;
    font-weight: bold;
}
.positive-bg {
    background-color: green !important;
    font-weight: bold;
}
.negative-bg {
    background-color: red !important;
    font-weight: bold;
}
.negative-pnl {
    color: red !important;
    font-weight: bold;
}
.dataframe-fix-small .table-wrap {
min-height: 150px;
max-height: 150px;
}
.dataframe-fix .table-wrap {
min-height: 200px;
max-height: 200px;
}
footer{display:none !important}
"""


js = """
function refresh() {
    const url = new URL(window.location);

    if (url.searchParams.get('__theme') !== 'dark') {
        url.searchParams.set('__theme', 'dark');
        window.location.href = url.href;
    }
}
"""

class Color(Enum):
    RED = "#dd0000"
    GREEN = "#00dd00"
    YELLOW = "#dddd00"
    BLUE = "#0000ee"
    MAGENTA = "#aa00dd"
    CYAN = "#00dddd"
    WHITE = "#87CEEB"

# api_key = os.getenv("ALPACA_API_KEY")
# secret_key = os.getenv("ALPACA_SECRET_KEY")
# if not api_key or not secret_key:
#     print(
#         "Missing Alpaca API credentials. "
#         "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables."
#     )

    

# client = TradingClient(
#     api_key=api_key,
#     secret_key=secret_key,
#     paper=os.getenv("ALPACA_PAPER", "true").lower() == "true"
# )

_client_lock = threading.Lock()
_client = None

def _create_client():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if not api_key or not secret_key:
        raise RuntimeError("Missing Alpaca credentials in environment (ALPACA_API_KEY/ALPACA_SECRET_KEY)")

    return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)

def get_alpaca_client():
    """Return a singleton TradingClient. Initialize on first use."""
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client
        try:
            _client = _create_client()
            print("Alpaca client initialized in PID:", os.getpid())
            return _client
        except Exception as e:
            # Log and re-raise so callers can decide how to handle
            print(f"[util.get_alpaca_client] Failed to initialize Alpaca client in PID {os.getpid()}: {e}")
            _client = None
            raise

def alpaca_is_market_open() -> bool:
    clock = get_alpaca_client().get_clock()
    return clock.is_open

def alpaca_cancel_stale_orders():
    """Cancels orders stuck in 'new' state before next trade."""
    req = GetOrdersRequest(status=OrderStatus.OPEN)
    orders = get_alpaca_client().get_orders(filter=req)
    print(f"Order stale state {orders}")
    count = 0
    for o in orders:
        if o.status == "new":
            get_alpaca_client().cancel_order_by_id(o.id)
            count += 1
    return count