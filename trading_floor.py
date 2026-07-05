import threading
from traders import Trader
from typing import List
import asyncio
from datetime import timedelta
from tracers import LogTracer
from agents import set_trace_processors
from dotenv import load_dotenv
from util import stop_event, alpaca_is_market_open, alpaca_get_clock
import os

load_dotenv(override=True)

RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
RUN_EVEN_WHEN_MARKET_IS_CLOSED = (
    os.getenv("RUN_EVEN_WHEN_MARKET_IS_CLOSED", "false").strip().lower() == "true"
)
USE_MANY_MODELS = os.getenv("USE_MANY_MODELS", "false").strip().lower() == "true"

# Scheduling mode:
#   "open_close" (default) -> run exactly twice per trading day: at the open and
#                             CLOSE_LEAD_MINUTES before the close.
#   "interval"             -> legacy fixed-frequency loop (RUN_EVERY_N_MINUTES).
RUN_SCHEDULE = os.getenv("RUN_SCHEDULE", "open_close").strip().lower()
# Minutes after the opening bell to fire the first run (0 = exactly at the open).
OPEN_DELAY_MINUTES = float(os.getenv("OPEN_DELAY_MINUTES", "0"))
# Minutes BEFORE the close to fire the second run, so orders can still fill while
# the market is open (firing exactly at the close means orders wait for next day).
CLOSE_LEAD_MINUTES = float(os.getenv("CLOSE_LEAD_MINUTES", "10"))
# Run one cycle immediately when the floor is started, instead of waiting for the
# next open/close. Gives instant feedback when you click "Start". (open_close mode)
RUN_ON_START = os.getenv("RUN_ON_START", "true").strip().lower() == "true"

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

# Models are OpenRouter "provider/model" IDs — every trader is routed through
# OpenRouter (see traders.get_model), so a single OPENROUTER_API_KEY unlocks all
# of them and no per-provider keys are needed. Configure via env:
#   USE_MANY_MODELS=false -> every trader uses TRADER_MODEL
#   USE_MANY_MODELS=true  -> traders use the comma-separated TRADER_MODELS in order
DEFAULT_TRADER_MODEL = os.getenv("TRADER_MODEL", "openai/gpt-4.1-mini")
DEFAULT_TRADER_MODELS = (
    "openai/gpt-4.1-mini,deepseek/deepseek-chat,"
    "google/gemini-2.5-flash,x-ai/grok-3-mini-beta"
)


def _short_name(model_id: str) -> str:
    """Dashboard label derived from the model id, e.g. 'openai/gpt-4.1-mini' -> 'gpt-4.1-mini'."""
    return model_id.split("/")[-1]


def _fit_to_traders(models: list[str]) -> list[str]:
    """Force a model list to exactly len(names) entries (truncate, or pad with the last)."""
    models = [m for m in models if m] or [DEFAULT_TRADER_MODEL]
    models = models[: len(names)]
    while len(models) < len(names):
        models.append(models[-1])
    return models


if USE_MANY_MODELS:
    model_names = _fit_to_traders(
        [m.strip() for m in os.getenv("TRADER_MODELS", DEFAULT_TRADER_MODELS).split(",")]
    )
else:
    model_names = [DEFAULT_TRADER_MODEL] * len(names)

short_model_names = [_short_name(m) for m in model_names]


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
    # Replace (not append) the processor list so the SDK's default OpenAI trace
    # exporter is dropped — we run fully on OpenRouter and have no OpenAI key.
    set_trace_processors([LogTracer()])
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


def _select_next_event(clock, fired: set):
    """Pick the soonest not-yet-fired event as (name, target_time, event_date).

    `target_time` already folds in OPEN_DELAY_MINUTES / CLOSE_LEAD_MINUTES. Returns
    None if every candidate event has already been fired. Pure function — no I/O —
    so the scheduling decision can be unit-tested without a live clock.
    """
    candidates = []
    if clock.next_open:
        candidates.append(
            ("open", clock.next_open + timedelta(minutes=OPEN_DELAY_MINUTES), clock.next_open.date())
        )
    if clock.next_close:
        candidates.append(
            ("close", clock.next_close - timedelta(minutes=CLOSE_LEAD_MINUTES), clock.next_close.date())
        )
    pending = [c for c in candidates if (c[0], c[2]) not in fired]
    if not pending:
        return None
    return min(pending, key=lambda c: c[1])


async def run_on_open_close():
    """Run all traders exactly twice per trading day: at the open, and
    CLOSE_LEAD_MINUTES before the close. Driven by the Alpaca market clock, so it
    follows the real NYSE calendar (holidays, half-days) automatically.
    """
    set_trace_processors([LogTracer()])
    traders = create_traders()

    # Bridge the threading stop_event into this asyncio loop (same pattern as the
    # interval scheduler) so a stop request wakes us out of a long sleep.
    async_stop_event = asyncio.Event()

    def stop_callback():
        if stop_event.is_set():
            async_stop_event.set()
        else:
            asyncio.get_running_loop().call_later(1, stop_callback)

    asyncio.get_running_loop().call_later(1, stop_callback)

    async def sleep_or_stop(seconds: float):
        """Sleep up to `seconds`, but return immediately if a stop is requested."""
        try:
            await asyncio.wait_for(async_stop_event.wait(), timeout=max(0.0, seconds))
        except asyncio.TimeoutError:
            pass

    # (event_name, event_date) pairs already run today, to prevent double-firing.
    fired: set = set()

    async def run_cycle(label: str, is_open: bool):
        print(f"[scheduler] {label} trigger — running trade cycle (market_open={is_open})")
        await asyncio.gather(*[trader.run() for trader in traders])

    # Kickoff: run one cycle immediately on start so clicking "Start" executes
    # right away — but ONLY while the market is open. Running a full research+trade
    # cycle while closed wastes LLM tokens and would queue orders that fill at the
    # next open on stale analysis, so we skip it (override with
    # RUN_EVEN_WHEN_MARKET_IS_CLOSED for off-hours paper testing). If the market is
    # already open, count it as today's open so the scheduled open won't re-fire.
    if RUN_ON_START and not async_stop_event.is_set():
        try:
            clock = await asyncio.to_thread(alpaca_get_clock)
            is_open, today, next_open = bool(clock.is_open), clock.timestamp.date(), clock.next_open
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] Startup clock fetch failed: {e}; skipping kickoff")
            is_open, today, next_open = False, None, None

        if is_open or RUN_EVEN_WHEN_MARKET_IS_CLOSED:
            if is_open and today is not None:
                fired.add(("open", today))
            await run_cycle("STARTUP (floor started)", is_open)
            await sleep_or_stop(5)
        else:
            when = next_open.isoformat() if next_open else "the next open"
            print(f"[scheduler] Floor started while market CLOSED — skipping orders & research; "
                  f"first run at {when}.")

    while not async_stop_event.is_set():
        try:
            clock = await asyncio.to_thread(alpaca_get_clock)
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] Could not fetch Alpaca clock: {e}; retrying in 60s")
            await sleep_or_stop(60)
            continue

        now = clock.timestamp

        event = _select_next_event(clock, fired)
        if event is None:
            await sleep_or_stop(60)
            continue

        name, target, ev_date = event
        wait_s = (target - now).total_seconds()

        if wait_s > 1:
            print(f"[scheduler] Next run: {name} at {target.isoformat()} (in {wait_s / 3600:.2f}h)")
            # Cap the sleep at 1h so we periodically re-read the clock (handles
            # clock drift, holiday changes, and stop requests promptly).
            await sleep_or_stop(min(wait_s, 3600))
            continue

        # Target reached — run once and remember it so we don't re-fire.
        fired.add((name, ev_date))
        await run_cycle(name.upper(), clock.is_open)

        # Drop stale keys so the set can't grow without bound.
        cutoff = now.date() - timedelta(days=2)
        fired = {k for k in fired if k[1] >= cutoff}

        # Buffer so the open/close boundary is firmly crossed before re-evaluating.
        await sleep_or_stop(60)

    print("Open/close scheduler terminated safely.")


async def run_scheduler():
    """Dispatch to the configured scheduling mode."""
    if RUN_SCHEDULE == "interval":
        await run_every_n_minutes()
        return
    if RUN_SCHEDULE != "open_close":
        print(f"[scheduler] Unknown RUN_SCHEDULE={RUN_SCHEDULE!r}; defaulting to open_close")
    await run_on_open_close()


if __name__ == "__main__":
    print(f"Starting scheduler (mode={RUN_SCHEDULE})")
    asyncio.run(run_scheduler())
