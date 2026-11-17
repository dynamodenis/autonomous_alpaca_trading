"""Periodic P/L snapshots for every trader, so the dashboard charts keep moving.

A trader's own run only records a point when it starts (and after each fill),
which with the open/close schedule is a couple of points a day. This loop adds
one for every trader every SNAPSHOT_INTERVAL_SECONDS while the market is open.

It only ever INSERTs into portfolio_snapshots. It must never save an account
row: the MCP server subprocesses rewrite that row when they record a fill, and
a concurrent read-modify-write from here could drop a transaction.
"""

import asyncio
import os

from accounts import Account
from prices import live_prices
from trading_floor import names
from util import alpaca_get_clock

# 0 (or less) disables the loop.
SNAPSHOT_INTERVAL_SECONDS = float(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "300"))


def snapshot_all_traders() -> int:
    """Record one P/L point per trader at current prices. Returns how many were written."""
    prices = live_prices(max_age=0)
    if prices is None:
        return 0
    written = 0
    for name in names:
        try:
            if Account.get(name).record_snapshot(prices):
                written += 1
        except Exception as e:  # noqa: BLE001
            print(f"[snapshots] {name}: {e}")
    return written


def _tick() -> None:
    # Outside market hours prices barely move and the dashboard stops polling;
    # skipping also lets a scale-to-zero database (Neon) sleep overnight.
    if alpaca_get_clock().is_open:
        snapshot_all_traders()


async def run_snapshot_loop() -> None:
    """Run until cancelled. Errors are logged and retried on the next tick."""
    if SNAPSHOT_INTERVAL_SECONDS <= 0:
        print("[snapshots] disabled (SNAPSHOT_INTERVAL_SECONDS <= 0)")
        return
    print(f"[snapshots] recording trader P/L every {SNAPSHOT_INTERVAL_SECONDS:g}s while the market is open")
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception as e:  # noqa: BLE001
            print(f"[snapshots] tick failed: {e}")
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
