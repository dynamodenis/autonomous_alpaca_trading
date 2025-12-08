import threading
from traders import Trader
from typing import List
import asyncio
from tracers import LogTracer
from agents import add_trace_processor
from dotenv import load_dotenv
from util import stop_event, alpaca_is_market_open
import os

load_dotenv(override=True)

RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
RUN_EVEN_WHEN_MARKET_IS_CLOSED = (
    os.getenv("RUN_EVEN_WHEN_MARKET_IS_CLOSED", "false").strip().lower() == "true"
)
USE_MANY_MODELS = os.getenv("USE_MANY_MODELS", "false").strip().lower() == "true"

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

if USE_MANY_MODELS:
    model_names = [
        "gpt-4.1-mini",
        "deepseek-chat",
        "gemini-2.5-flash-preview-04-17",
        "grok-3-mini-beta",
    ]
    short_model_names = ["GPT 4.1 Mini", "DeepSeek V3", "Gemini 2.5 Flash", "Grok 3 Mini"]
else:
    model_names = ["gpt-4.1-mini"] * 4
    short_model_names = ["GPT 4.1 mini"] * 4


def create_traders() -> List[Trader]:
    traders = []
    for name, lastname, model_name in zip(names, lastnames, model_names):
        traders.append(Trader(name, lastname, model_name))
    return traders


async def run_every_n_minutes():
    """
    Runs trading agents every N minutes, cooperatively stopping when signaled.
    """

    print(
        "Thread env keys present:",
        bool(os.getenv("ALPACA_API_KEY")),
        bool(os.getenv("ALPACA_SECRET_KEY"))
    )
    add_trace_processor(LogTracer())
    traders = create_traders()
    
    # Create an asyncio Event to link the thread signal to the loop
    async_stop_event = asyncio.Event()

    # Function to set the asyncio event from the thread's loop
    def stop_callback():
        # This function runs in the context of the running asyncio loop
        if stop_event.is_set():
            async_stop_event.set()
        else:
            # Re-schedule this check if the event hasn't been set
            loop = asyncio.get_running_loop()
            loop.call_later(1, stop_callback)

    # Start the periodic check for the threading.Event
    loop = asyncio.get_running_loop()
    loop.call_later(1, stop_callback)

    while not async_stop_event.is_set():
        if RUN_EVEN_WHEN_MARKET_IS_CLOSED or alpaca_is_market_open():
            print("Running trade cycle...")
            # Run agents
            await asyncio.gather(*[trader.run() for trader in traders])
        else:
            print("Market is closed, skipping run")

        # Wait for the next interval OR the stop signal
        try:
            # Wait for the interval, but be interruptible by async_stop_event.set()
            await asyncio.wait_for(async_stop_event.wait(), timeout=RUN_EVERY_N_MINUTES * 60)
        except asyncio.TimeoutError:
            # Timeout hit, continue to the next iteration
            continue
        except Exception:
            # The async_stop_event was set, or another issue occurred
            break
        
    print("Agent trading loop terminated safely.")


if __name__ == "__main__":
    print(f"Starting scheduler to run every {RUN_EVERY_N_MINUTES} minutes")
    asyncio.run(run_every_n_minutes())
