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

api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

client = TradingClient(
    api_key=api_key,
    secret_key=secret_key,
    paper=os.getenv("ALPACA_PAPER", "true").lower() == "true"
)

def alpaca_is_market_open() -> bool:
    clock = client.get_clock()
    return clock.is_open

def alpaca_cancel_stale_orders():
    """Cancels orders stuck in 'new' state before next trade."""
    req = GetOrdersRequest(status=OrderStatus.OPEN)
    orders = client.get_orders(filter=req)
    print(f"Order stale state {orders}")
    count = 0
    for o in orders:
        if o.status == "new":
            client.cancel_order_by_id(o.id)
            count += 1
    return count