"""Persistence layer: accounts, logs, market cache, meta, portfolio snapshots.

Backend is chosen from the DATABASE_URL env var:

  * ``postgres://`` / ``postgresql://`` -> Postgres via psycopg (hosted, e.g. Neon).
    This is what you want on Hugging Face Spaces, whose filesystem is wiped on
    every restart.
  * unset                               -> local SQLite file ``accounts.db``
    (zero-config for local development).

All public functions have the same signatures and return shapes on both
backends, so callers never need to know which one is active.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "accounts.db")

IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
BACKEND = "postgres" if IS_POSTGRES else "sqlite"


# ── Connection handling ──────────────────────────────────────────────────────

if IS_POSTGRES:
    from psycopg_pool import ConnectionPool

    # Small pool: a handful of traders + the API share it.
    #  * autocommit: every public function is a single statement, so a separate
    #    COMMIT round trip per call is pure overhead (noticeable on Neon).
    #  * check: validates a connection before handing it out. Neon scales the
    #    compute to zero after ~5 idle minutes, killing server-side connections,
    #    and this turns that into a transparent reconnect instead of an error.
    #  * max_idle: drop pooled connections idle for 4 min, i.e. before Neon does.
    def _configure(conn):
        conn.autocommit = True

    _pool = ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=1,
        max_size=int(os.getenv("DATABASE_POOL_SIZE", "4")),
        max_idle=240,
        configure=_configure,
        check=ConnectionPool.check_connection,
        open=True,
    )

    @contextmanager
    def _connect():
        with _pool.connection() as conn:
            yield conn

else:
    @contextmanager
    def _connect():
        conn = sqlite3.connect(SQLITE_PATH)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _q(sql: str) -> str:
    """Rewrite ``?`` placeholders to psycopg's ``%s`` when on Postgres."""
    return sql.replace("?", "%s") if IS_POSTGRES else sql


def _execute(sql: str, params: tuple = ()):
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        return cur


def _fetchone(sql: str, params: tuple = ()):
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        return cur.fetchone()


def _fetchall(sql: str, params: tuple = ()) -> list:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        return cur.fetchall()


# ── Schema ───────────────────────────────────────────────────────────────────

# Timestamps are stored in UTC and always *read back* as 'YYYY-MM-DD HH:MM:SS'
# strings so the API payload is byte-identical across backends.
if IS_POSTGRES:
    _SCHEMA = [
        "CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, account TEXT)",
        """CREATE TABLE IF NOT EXISTS logs (
               id BIGSERIAL PRIMARY KEY,
               name TEXT,
               datetime TIMESTAMPTZ NOT NULL DEFAULT now(),
               type TEXT,
               message TEXT
           )""",
        "CREATE INDEX IF NOT EXISTS logs_name_datetime ON logs (name, datetime DESC)",
        "CREATE TABLE IF NOT EXISTS market (date TEXT PRIMARY KEY, data TEXT)",
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
        """CREATE TABLE IF NOT EXISTS portfolio_snapshots (
               id BIGSERIAL PRIMARY KEY,
               name TEXT NOT NULL,
               ts TIMESTAMPTZ NOT NULL DEFAULT now(),
               portfolio_value DOUBLE PRECISION NOT NULL,
               pnl DOUBLE PRECISION NOT NULL
           )""",
        "CREATE INDEX IF NOT EXISTS snapshots_name_ts ON portfolio_snapshots (name, ts)",
    ]
    _NOW = "now()"
    _TS_OUT = "to_char({col} AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"
else:
    _SCHEMA = [
        "CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, account TEXT)",
        """CREATE TABLE IF NOT EXISTS logs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT,
               datetime DATETIME,
               type TEXT,
               message TEXT
           )""",
        "CREATE INDEX IF NOT EXISTS logs_name_datetime ON logs (name, datetime DESC)",
        "CREATE TABLE IF NOT EXISTS market (date TEXT PRIMARY KEY, data TEXT)",
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
        """CREATE TABLE IF NOT EXISTS portfolio_snapshots (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               ts DATETIME NOT NULL,
               portfolio_value REAL NOT NULL,
               pnl REAL NOT NULL
           )""",
        "CREATE INDEX IF NOT EXISTS snapshots_name_ts ON portfolio_snapshots (name, ts)",
    ]
    _NOW = "datetime('now')"
    _TS_OUT = "{col}"


def init_schema() -> None:
    with _connect() as conn:
        cur = conn.cursor()
        for stmt in _SCHEMA:
            cur.execute(stmt)


init_schema()
print(f"[database] backend={BACKEND}" + ("" if IS_POSTGRES else f" path={SQLITE_PATH}"))


# ── Accounts ─────────────────────────────────────────────────────────────────

def write_account(name, account_dict):
    _execute(
        """INSERT INTO accounts (name, account) VALUES (?, ?)
           ON CONFLICT(name) DO UPDATE SET account=excluded.account""",
        (name.lower(), json.dumps(account_dict)),
    )


def read_account(name):
    row = _fetchone("SELECT account FROM accounts WHERE name = ?", (name.lower(),))
    return json.loads(row[0]) if row else None


# ── Logs ─────────────────────────────────────────────────────────────────────

def write_log(name: str, type: str, message: str):
    """Append a log entry (timestamped server-side, UTC)."""
    _execute(
        f"INSERT INTO logs (name, datetime, type, message) VALUES (?, {_NOW}, ?, ?)",
        (name.lower(), type, message),
    )


def read_log(name: str, last_n=10):
    """Most recent ``last_n`` entries for ``name`` as (datetime, type, message),
    oldest first."""
    rows = _fetchall(
        f"""SELECT {_TS_OUT.format(col='datetime')}, type, message FROM logs
            WHERE name = ?
            ORDER BY datetime DESC, id DESC
            LIMIT ?""",
        (name.lower(), last_n),
    )
    return reversed(rows)


# ── Market cache ─────────────────────────────────────────────────────────────

def write_market(date: str, data: dict) -> None:
    _execute(
        """INSERT INTO market (date, data) VALUES (?, ?)
           ON CONFLICT(date) DO UPDATE SET data=excluded.data""",
        (date, json.dumps(data)),
    )


def read_market(date: str) -> dict | None:
    row = _fetchone("SELECT data FROM market WHERE date = ?", (date,))
    return json.loads(row[0]) if row else None


# ── Meta ─────────────────────────────────────────────────────────────────────

def write_meta(key: str, data: dict) -> None:
    _execute(
        """INSERT INTO meta (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, json.dumps(data)),
    )


def read_meta(key: str) -> dict | None:
    row = _fetchone("SELECT value FROM meta WHERE key = ?", (key,))
    return json.loads(row[0]) if row else None


# ── Portfolio snapshots (unbounded history) ──────────────────────────────────
#
# The account JSON keeps a short, capped ``portfolio_value_time_series`` for the
# dashboard chart. This table is the full record: one row per account report,
# never trimmed, so you can chart or analyse the whole run.

def write_snapshot(name: str, portfolio_value: float, pnl: float) -> None:
    _execute(
        f"INSERT INTO portfolio_snapshots (name, ts, portfolio_value, pnl) VALUES (?, {_NOW}, ?, ?)",
        (name.lower(), float(portfolio_value), float(pnl)),
    )


def read_snapshots(name: str, since: str | None = None, limit: int | None = None) -> list[dict]:
    """Snapshots for ``name`` oldest-first.

    Args:
        since: optional ISO date/datetime lower bound (inclusive), e.g. '2026-01-01'.
        limit: if given, return only the most recent ``limit`` rows.
    """
    ts_out = _TS_OUT.format(col="ts")
    where = "WHERE name = ?"
    params: list = [name.lower()]
    if since:
        where += " AND ts >= ?"
        params.append(since)
    if limit:
        sql = f"""SELECT ts_text, portfolio_value, pnl FROM (
                      SELECT {ts_out} AS ts_text, id, portfolio_value, pnl FROM portfolio_snapshots
                      {where} ORDER BY ts DESC, id DESC LIMIT ?
                  ) recent ORDER BY id ASC"""
        params.append(limit)
    else:
        sql = f"""SELECT {ts_out}, portfolio_value, pnl FROM portfolio_snapshots
                  {where} ORDER BY ts ASC, id ASC"""
    rows = _fetchall(sql, tuple(params))
    return [{"timestamp": ts, "portfolio_value": value, "pnl": pnl} for ts, value, pnl in rows]
