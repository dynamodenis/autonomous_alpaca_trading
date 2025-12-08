from hmac import trans_36
import gradio as gr
from util import css, js, Color
import pandas as pd
from trading_floor import names, lastnames, short_model_names
import plotly.express as px
from accounts import Account, INITIAL_BALANCE
from database import read_log
import threading
from trading_floor import run_every_n_minutes
from util import stop_event
import asyncio
import os

mapper = {
    "trace": Color.WHITE,
    "agent": Color.CYAN,
    "function": Color.GREEN,
    "generation": Color.YELLOW,
    "response": Color.MAGENTA,
    "account": Color.RED,
}

# ---------------- HuggingFace Spaces ENV FIX ----------------
REQUIRED_KEYS = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER"]

def force_env():
    for key in REQUIRED_KEYS:
        val = os.getenv(key)
        if val:
            os.environ[key] = val  # force propagate to threads & subprocesses
        else:
            print(f"[HF WARNING] Missing env key: {key}")

force_env()
# -------------------------------------------------------------


trading_thread = None

class Trader:
    def __init__(self, name: str, lastname: str, model_name: str):
        self.name = name
        self.lastname = lastname
        self.model_name = model_name
        self.account = Account.get(name)

    def reload(self):
        self.account = Account.get(self.name)

    def get_title(self) -> str:
        return f"<div style='text-align: center;font-size:34px;'>{self.name}<span style='color:#ccc;font-size:24px;'> ({self.model_name}) - {self.lastname}</span></div>"

    def get_strategy(self) -> str:
        return self.account.get_strategy()

    def get_portfolio_value_df(self) -> pd.DataFrame:
        df = pd.DataFrame(self.account.portfolio_value_time_series, columns=["datetime", "value"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        return df

    def get_portfolio_value_chart(self):
        df = self.get_portfolio_value_df()
        fig = px.line(df, x="datetime", y="value")
        margin = dict(l=40, r=20, t=20, b=40)
        fig.update_layout(
            height=300,
            margin=margin,
            xaxis_title=None,
            yaxis_title=None,
            paper_bgcolor="#bbb",
            plot_bgcolor="#dde",
        )
        fig.update_xaxes(tickformat="%m/%d", tickangle=45, tickfont=dict(size=8))
        fig.update_yaxes(tickfont=dict(size=8), tickformat=",.0f")
        return fig

    def get_holdings_df(self) -> pd.DataFrame:
        """Convert holdings to DataFrame for display"""
        holdings = self.account.get_holdings()
        if not holdings:
            return pd.DataFrame(columns=["Symbol", "Quantity"])

        df = pd.DataFrame(
            [{"Symbol": symbol, "Quantity": quantity} for symbol, quantity in holdings.items()]
        )
        return df

    def get_transactions_df(self) -> pd.DataFrame:
        """Convert transactions to DataFrame for display"""
        transactions = self.account.list_transactions()
        if not transactions:
            return pd.DataFrame(columns=["Timestamp", "Symbol", "Quantity", "Price", "Rationale"])

        return pd.DataFrame(transactions)

    def get_portfolio_value(self) -> str:
        """Calculate total portfolio value based on current prices"""
        initial_value = INITIAL_BALANCE
        portfolio_value = self.account.calculate_portfolio_value() or 0.0
        pnl = self.account.calculate_profit_loss(portfolio_value) or 0.0
        color = "green" if pnl >= 0 else "red"
        emoji = "⬆" if pnl >= 0 else "⬇"
        return f"<div style='text-align: center;background-color:{color};'><span style='font-size:32px'>${portfolio_value:,.0f}</span><span style='font-size:24px'>&nbsp;&nbsp;&nbsp;{emoji}&nbsp;${pnl:,.0f}</span></div>"

    def get_logs(self, previous=None) -> str:
        logs = read_log(self.name, last_n=13)
        response = ""
        for log in logs:
            timestamp, type, message = log
            color = mapper.get(type, Color.WHITE).value
            response += f"<span style='color:{color}'>{timestamp} : [{type}] {message}</span><br/>"
        response = f"<div style='height:250px; overflow-y:auto;'>{response}</div>"
        if response != previous:
            return response
        return gr.update()


class TraderView:
    def __init__(self, trader: Trader):
        self.trader = trader
        self.portfolio_value = None
        self.chart = None
        self.holdings_table = None
        self.transactions_table = None

    def make_ui(self):
        with gr.Column():
            gr.HTML(self.trader.get_title())
            with gr.Row():
                self.portfolio_value = gr.HTML(self.trader.get_portfolio_value)
            with gr.Row():
                self.chart = gr.Plot(
                    self.trader.get_portfolio_value_chart, container=True, show_label=False
                )
            with gr.Row(variant="panel"):
                self.log = gr.HTML(self.trader.get_logs)
            with gr.Row():
                self.holdings_table = gr.Dataframe(
                    value=self.trader.get_holdings_df,
                    label="Holdings",
                    headers=["Symbol", "Quantity"],
                    row_count=(5, "dynamic"),
                    col_count=2,
                    max_height=300,
                    elem_classes=["dataframe-fix-small"],
                )
            with gr.Row():
                self.transactions_table = gr.Dataframe(
                    value=self.trader.get_transactions_df,
                    label="Recent Transactions",
                    headers=["Timestamp", "Symbol", "Quantity", "Price", "Rationale"],
                    row_count=(5, "dynamic"),
                    col_count=5,
                    max_height=300,
                    elem_classes=["dataframe-fix"],
                )

        timer = gr.Timer(value=120)
        timer.tick(
            fn=self.refresh,
            inputs=[],
            outputs=[
                self.portfolio_value,
                self.chart,
                self.holdings_table,
                self.transactions_table,
            ],
            show_progress="hidden",
            queue=False,
        )
        log_timer = gr.Timer(value=0.5)
        log_timer.tick(
            fn=self.trader.get_logs,
            inputs=[self.log],
            outputs=[self.log],
            show_progress="hidden",
            queue=False,
        )

    def refresh(self):
        self.trader.reload()
        return (
            self.trader.get_portfolio_value(),
            self.trader.get_portfolio_value_chart(),
            self.trader.get_holdings_df(),
            self.trader.get_transactions_df(),
        )
# --- Add this setup block ---
MEMORY_DIR = "memory"
def setup_directories():
    """Ensures the directory for the libSQL databases exists."""
    if not os.path.exists(MEMORY_DIR):
        try:
            os.makedirs(MEMORY_DIR, exist_ok=True)
            print(f"Created directory: {MEMORY_DIR}/")
        except OSError as e:
            # Important: Log the error if directory creation fails (e.g., due to permissions)
            print(f"Error creating directory {MEMORY_DIR}: {e}")
            raise

def stop_trading_thread():
    global trading_thread

    if trading_thread is None or not trading_thread.is_alive():
        return "🛑 Trading floor is not running."

    print("Stopping trading floor...")
    
    # 1. Set the stop signal
    stop_event.set()
    
    # 2. Wait for the thread to finish its current task and exit the loop safely
    trading_thread.join(timeout=10) # Wait up to 10 seconds for graceful exit
    
    if trading_thread.is_alive():
        return "❌ Trading floor thread failed to stop gracefully within 10 seconds."
    else:
        trading_thread = None # Clear the variable
        return "✅ Trading floor stopped successfully."

def start_trading_floor_and_thread():
    global trading_thread

    # check is thead is running
    if trading_thread is not None and trading_thread.is_alive():
        return "⚠️ Trading floor is already running."

    # Reset the stop event and create directory
    stop_event.clear()
    setup_directories()

    # 3. Define the thread's target function (wrapper to pass the event)
    def target_wrapper():
        # re-inject the environment variables
        force_env()
        # The target function now correctly passes the stop_event
        try:
            asyncio.run(run_every_n_minutes())
        except Exception as e:
            print(f"Error running trading floor: {e}")
            return "❌ Trading floor failed to start."

    # 4. Create and start the thread
    trading_thread = threading.Thread(target=target_wrapper, daemon=True)
    trading_thread.start()
    return "🚀 Trading floor started."


# Main UI construction
def create_ui():
    """Create the main Gradio UI for the trading simulation"""
    print(f"Stop event {stop_event.is_set()}")

    traders = [
        Trader(trader_name, lastname, model_name)
        for trader_name, lastname, model_name in zip(names, lastnames, short_model_names)
    ]
    trader_views = [TraderView(trader) for trader in traders]

    # stop_btn = gr.Button("Stop Trading Floor", variant="stop")
    # stop_btn.click(fn=lambda: stop_trading_floor(), inputs=[], outputs=[])

    with gr.Blocks(
        title="Traders", css=css, js=js, theme=gr.themes.Default(primary_hue="sky"), fill_width=True
    ) as ui:

        with gr.Row():
            start_btn = gr.Button("Start Trading Floor 🚀", variant="primary")
            stop_btn = gr.Button("Stop Trading Floor 🛑", variant="stop")

        # Add Status Output
        thread_status = gr.Textbox(label="Thread Status", value="Ready to start.", interactive=False)

        # Link buttons to functions
        start_btn.click(
            fn=start_trading_floor_and_thread, 
            outputs=[thread_status], 
            show_progress="hidden"
        )
        
        stop_btn.click(
            fn=stop_trading_thread, 
            outputs=[thread_status], 
            show_progress="hidden"
        )

        with gr.Row():
            for trader_view in trader_views:
                trader_view.make_ui()

    return ui


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(inbrowser=True)
