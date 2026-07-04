"""Lifecycle management for the autonomous trading floor.

Runs `trading_floor.run_every_n_minutes` in a background daemon thread and
exposes start/stop/status helpers used by the FastAPI layer. Lifted out of the
old Gradio `app.py` so the trading loop is UI-agnostic.
"""

import asyncio
import os
import threading

from trading_floor import run_scheduler
from util import stop_event

# ---------------- HuggingFace Spaces / subprocess ENV propagation ----------------
REQUIRED_KEYS = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER"]


def force_env():
    """Force-propagate required env vars to threads & spawned MCP subprocesses."""
    for key in REQUIRED_KEYS:
        val = os.getenv(key)
        if val:
            os.environ[key] = val
        else:
            print(f"[WARNING] Missing env key: {key}")


MEMORY_DIR = "memory"


def setup_directories():
    """Ensure the directory for the per-trader libSQL databases exists."""
    if not os.path.exists(MEMORY_DIR):
        try:
            os.makedirs(MEMORY_DIR, exist_ok=True)
            print(f"Created directory: {MEMORY_DIR}/")
        except OSError as e:
            print(f"Error creating directory {MEMORY_DIR}: {e}")
            raise


_trading_thread: threading.Thread | None = None


def is_floor_running() -> bool:
    return _trading_thread is not None and _trading_thread.is_alive()


def start_trading_floor() -> str:
    global _trading_thread

    if is_floor_running():
        return "⚠️ Trading floor is already running."

    # Reset the stop event and ensure the memory directory exists
    stop_event.clear()
    setup_directories()

    def target_wrapper():
        # Re-inject env vars into the new thread before spawning subprocesses
        force_env()
        try:
            asyncio.run(run_scheduler())
        except Exception as e:
            print(f"Error running trading floor: {e}")

    _trading_thread = threading.Thread(target=target_wrapper, daemon=True)
    _trading_thread.start()
    return "🚀 Trading floor started."


def stop_trading_floor() -> str:
    global _trading_thread

    if not is_floor_running():
        return "🛑 Trading floor is not running."

    print("Stopping trading floor...")

    # 1. Signal the loop to stop
    stop_event.set()

    # 2. Wait for the thread to exit the loop gracefully
    _trading_thread.join(timeout=10)

    if _trading_thread.is_alive():
        return "❌ Trading floor thread failed to stop gracefully within 10 seconds."

    _trading_thread = None
    return "✅ Trading floor stopped successfully."
