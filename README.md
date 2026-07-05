---
title: Alpaca Trading Floor API
emoji: 🚀
colorFrom: red
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# 🤖 AI Trading Floor

An autonomous multi-agent trading simulation where AI traders powered by different
language models compete in the stock market. Each AI develops its own strategy and
makes real-time decisions against a live Alpaca paper-trading account.

The project is split into a **Python/FastAPI backend** (repo root — runs the agents +
MCP tools and exposes a REST API) and a **React frontend** (`frontend/`, the dashboard).
They are deployed and run independently: the backend deploys to Hugging Face Spaces
(Docker) straight from this branch, and Cloudflare Pages builds the frontend from the
`frontend/` subdirectory.

## 🏗️ Architecture

```
┌──────────────────────────┐         REST / JSON          ┌──────────────────────────┐
│   frontend/  (React+TS)   │  ───────────────────────────▶│   backend/  (FastAPI)     │
│   Dashboard, polling UI   │ ◀───────────────────────────  │   /api/* endpoints        │
└──────────────────────────┘                               └────────────┬─────────────┘
                                                                         │
                                                          ┌──────────────┴───────────────┐
                                                          │  Trading floor (bg thread)    │
                                                          │  4 agents × MCP tool servers  │
                                                          └──────────────┬───────────────┘
                                                ┌────────┬───────┬───────┴───────┐
                                            ┌───▼──┐ ┌──▼───┐ ┌──▼──┐ ┌──────────▼─┐
                                            │Alpaca│ │Market│ │Push │ │ Researcher │
                                            │ MCP  │ │ data │ │ MCP │ │ web+memory │
                                            └──────┘ └──────┘ └─────┘ └────────────┘
```

## 📂 Project structure

```
./                    # FastAPI backend at the repo root (Hugging Face Space)
├── api.py            # FastAPI app (REST endpoints, CORS)
├── floor_control.py  # Start/stop the trading-floor background thread
├── trading_floor.py  # Scheduler — runs the agents every N minutes
├── traders.py        # Trader/Researcher agent construction
├── templates.py      # Agent prompts & personalities
├── accounts*.py      # Portfolio bookkeeping + MCP account server
├── market*.py        # Market-data + MCP market server
├── push_server.py    # Pushover notification MCP server
├── mcp_params.py     # MCP server wiring (Alpaca, market, push, researcher)
├── database.py       # SQLite persistence (accounts, logs, market cache)
├── Dockerfile  requirements.txt  .env.example
├── BACKEND.md        # Backend setup, env vars, endpoint reference
└── frontend/         # React + TypeScript dashboard (Vite → Cloudflare Pages)
    ├── src/
    │   ├── api/         # Typed fetch client + backend payload types
    │   ├── components/  # TraderCard, PortfolioChart, SummaryBar, FloorControl…
    │   ├── hooks/       # usePolling — no-flicker interval polling
    │   ├── lib/  theme/ # Formatting helpers + per-trader theming
    │   └── App.tsx  index.css   # Layout + design system
    └── README.md        # Frontend setup & configuration
```

## 📊 Meet the traders

Each AI agent starts with **$10,000** and trades independently:

| Name | Personality | Model (multi-model mode) | Strategy Style |
|------|------------|--------------------------|----------------|
| **Warren Patience** | Conservative, long-term value investor | GPT-4.1 Mini | Patient, fundamental analysis |
| **George Bold** | Aggressive macro risk-taker | DeepSeek V3 | Bold contrarian moves |
| **Ray Systematic** | Data-driven quantitative trader | Gemini 2.5 Flash | Systematic, rule-based |
| **Cathie Crypto** | Innovation-focused growth investor | Grok 3 Mini | Disruptive tech & crypto ETFs |

In single-model mode (`USE_MANY_MODELS=false`) all four run on GPT-4.1 Mini.

## 🚀 Quick start

### 1. Backend (repo root)

```bash
cp .env.example .env          # then fill in your keys
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

API docs at `http://localhost:8000/docs`. See [`BACKEND.md`](BACKEND.md)
for the full environment-variable reference and endpoint list.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

In dev, Vite proxies `/api/*` to the backend on port 8000 (no CORS setup
needed) — just keep the backend running. The dashboard auto-polls every few
seconds and lets you start/stop the trading floor from the header. See
[`frontend/README.md`](frontend/README.md) for configuration and production
build/deploy notes.

## 🔌 API overview

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/traders` | Trader roster |
| `GET`  | `/api/traders/{name}` | One trader's account snapshot |
| `GET`  | `/api/traders/{name}/logs` | Recent log entries |
| `GET`  | `/api/dashboard` | All traders' accounts + logs in one payload |
| `GET`  | `/api/floor/status` | Whether the trading floor is running |
| `POST` | `/api/floor/start` · `/api/floor/stop` | Control the trading floor |

## ⚙️ Configuration

All configuration is via environment variables in `.env` at the repo root — see
[`.env.example`](.env.example) for the complete annotated list
(Alpaca, LLM providers, market data, push notifications, trading cadence, CORS).

## ⚖️ Disclaimer

**This is a simulation for educational and entertainment purposes only.**
Not financial advice. AI models can make irrational decisions. Do not use this for
actual investment decisions — always consult a qualified financial advisor.

## 📄 License

MIT License.

---

**Made with ❤️ by [DynamoDenis254](https://huggingface.co/dynamodenis254) · [LinkedIn](https://www.linkedin.com/in/dynamo-denis-mbugua-53304b197/)**
