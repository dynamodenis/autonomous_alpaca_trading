"""One-off: copy the local SQLite ``accounts.db`` into the Postgres DATABASE_URL.

Usage (DATABASE_URL in .env or the environment):

    uv run migrate_sqlite_to_postgres.py                 # migrate ./accounts.db
    uv run migrate_sqlite_to_postgres.py path/to/old.db  # another sqlite file
    uv run migrate_sqlite_to_postgres.py --append        # add logs even if the
                                                         # target already has some

Keyed tables (accounts, market, meta) are upserted, so re-running is safe.
Logs and snapshots are append-only, so by default the script refuses to copy
them into a target that already holds rows, to avoid duplicating history.
"""

import os
import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    sys.exit("DATABASE_URL is not set to a Postgres URL; nothing to migrate into.")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
APPEND = "--append" in sys.argv
SQLITE_PATH = args[0] if args else "accounts.db"
if not os.path.exists(SQLITE_PATH):
    sys.exit(f"SQLite file not found: {SQLITE_PATH}")

# Importing database creates the Postgres schema and the pool.
import database  # noqa: E402

assert database.IS_POSTGRES, "database module did not pick the Postgres backend"

src = sqlite3.connect(SQLITE_PATH)


def _sqlite_has(table: str) -> bool:
    return src.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


with database._connect() as conn:
    cur = conn.cursor()

    # ── keyed tables: upsert ────────────────────────────────────────────────
    n = 0
    for name, account in src.execute("SELECT name, account FROM accounts"):
        cur.execute(
            "INSERT INTO accounts (name, account) VALUES (%s, %s) "
            "ON CONFLICT(name) DO UPDATE SET account=excluded.account",
            (name, account),
        )
        n += 1
    print(f"accounts: {n} upserted")

    n = 0
    for date, data in src.execute("SELECT date, data FROM market"):
        cur.execute(
            "INSERT INTO market (date, data) VALUES (%s, %s) "
            "ON CONFLICT(date) DO UPDATE SET data=excluded.data",
            (date, data),
        )
        n += 1
    print(f"market: {n} upserted")

    n = 0
    for key, value in src.execute("SELECT key, value FROM meta"):
        cur.execute(
            "INSERT INTO meta (key, value) VALUES (%s, %s) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        n += 1
    print(f"meta: {n} upserted")

    # ── append-only tables ──────────────────────────────────────────────────
    cur.execute("SELECT count(*) FROM logs")
    existing = cur.fetchone()[0]
    if existing and not APPEND:
        print(f"logs: target already has {existing} rows; skipping (pass --append to add anyway)")
    else:
        rows = src.execute(
            "SELECT name, datetime, type, message FROM logs ORDER BY id"
        ).fetchall()
        # SQLite stored datetime('now') = UTC text; tell Postgres it's UTC.
        cur.executemany(
            "INSERT INTO logs (name, datetime, type, message) "
            "VALUES (%s, (%s::timestamp AT TIME ZONE 'UTC'), %s, %s)",
            rows,
        )
        print(f"logs: {len(rows)} copied")

    if _sqlite_has("portfolio_snapshots"):
        cur.execute("SELECT count(*) FROM portfolio_snapshots")
        existing = cur.fetchone()[0]
        if existing and not APPEND:
            print(f"portfolio_snapshots: target already has {existing} rows; skipping")
        else:
            rows = src.execute(
                "SELECT name, ts, portfolio_value, pnl FROM portfolio_snapshots ORDER BY id"
            ).fetchall()
            cur.executemany(
                "INSERT INTO portfolio_snapshots (name, ts, portfolio_value, pnl) "
                "VALUES (%s, (%s::timestamp AT TIME ZONE 'UTC'), %s, %s)",
                rows,
            )
            print(f"portfolio_snapshots: {len(rows)} copied")

    # Backfill snapshots from each account's embedded (capped) time series when
    # the table is still empty, so the history chart isn't blank on day one.
    cur.execute("SELECT count(*) FROM portfolio_snapshots")
    if cur.fetchone()[0] == 0:
        import json

        n = 0
        for name, account in src.execute("SELECT name, account FROM accounts"):
            acct = json.loads(account)
            series = acct.get("portfolio_value_time_series") or []
            # The embedded series has no P&L; derive it from the first point
            # (the sim's initial balance isn't stored alongside the series).
            base = series[0][1] if series else 0.0
            for ts, value in series:
                cur.execute(
                    "INSERT INTO portfolio_snapshots (name, ts, portfolio_value, pnl) "
                    "VALUES (%s, (%s::timestamp AT TIME ZONE 'UTC'), %s, %s)",
                    (name, ts, value, value - base),
                )
                n += 1
        print(f"portfolio_snapshots: backfilled {n} points from embedded account series")

    conn.commit()

print("done")
