# AI Trading Floor — Backend

FastAPI service that runs the autonomous multi-agent trading floor and exposes
its data and lifecycle controls as a REST API for the React frontend.

> Run all commands from this `backend/` directory. The MCP servers are spawned
> with cwd-relative paths (`uv run accounts_server.py`, `file:./memory/{name}.db`),
> so the working directory must be `backend/`.

## Setup

Create a `.env` (see the keys below), then install dependencies:

```bash
pip install -r requirements.txt
# or: uv pip install -r requirements.txt
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Alpaca brokerage (paper) credentials |
| `ALPACA_PAPER` | `true` (default) for paper trading |
| `OPENROUTER_API_KEY` | Required — all traders + researcher run through OpenRouter |
| `TRADER_MODEL` | Model for all traders when `USE_MANY_MODELS=false` (default `openai/gpt-4.1-mini`) |
| `TRADER_MODELS` | Comma-separated models (one per trader, in order) when `USE_MANY_MODELS=true` |
| `RESEARCHER_MODEL` | Cheap model for the Researcher sub-agent (default `openai/gpt-4.1-mini`) |
| `SEARCH_PROVIDER` | Researcher web search provider: `tavily` (default) or `brave` |
| `TAVILY_API_KEY` | Researcher web search (when `SEARCH_PROVIDER=tavily`, the default) |
| `BRAVE_API_KEY` | Researcher web search (when `SEARCH_PROVIDER=brave`) |
| `POLYGON_API_KEY`, `POLYGON_PLAN` | Market data (optional; falls back to random prices) |
| `PUSHOVER_USER`, `PUSHOVER_TOKEN` | Push notifications |
| `RUN_SCHEDULE` | `open_close` (default — run at the open and before close) or `interval` |
| `RUN_ON_START` | Run one cycle immediately when the floor starts (default `true`) |
| `OPEN_DELAY_MINUTES` | Minutes after the open to run (default `0`) |
| `CLOSE_LEAD_MINUTES` | Minutes before the close to run (default `10`, so orders can still fill) |
| `RUN_EVERY_N_MINUTES` | Trading cycle frequency, **interval mode only** (default `60`) |
| `RUN_EVEN_WHEN_MARKET_IS_CLOSED` | Interval mode only: `true`/`false` (default `false`) |
| `USE_MANY_MODELS` | `true`/`false` (default `false`) |
| `FRONTEND_ORIGINS` | Comma-separated CORS origins (default `*`) |

## Run

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Or via Docker (build with this directory as context):

```bash
docker build -t trading-floor-backend .
docker run --env-file .env -p 8000:8000 trading-floor-backend
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/traders` | Trader roster (name, lastname, model) |
| `GET`  | `/api/traders/{name}` | Account snapshot for one trader |
| `GET`  | `/api/traders/{name}/logs?limit=13` | Recent log entries (oldest → newest) |
| `GET`  | `/api/dashboard?log_limit=13` | All traders' accounts + logs in one payload |
| `GET`  | `/api/floor/status` | `{ running: bool }` |
| `POST` | `/api/floor/start` | Start the trading floor thread |
| `POST` | `/api/floor/stop` | Stop the trading floor thread |

Interactive docs at `http://localhost:8000/docs`.
