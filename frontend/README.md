# 🖥️ AI Trading Floor — Frontend

A React + TypeScript + Vite dashboard for the [AI Trading Floor](../README.md)
backend. It polls the FastAPI `/api/*` endpoints and renders each AI trader's
portfolio value, P/L, holdings, trades, and live activity log — plus a control
to start/stop the trading floor.

## ✨ Features

- **Live dashboard** — auto-polls `/api/dashboard` (default every 8s) with no
  flicker; the UI keeps the last good data through transient backend hiccups.
- **Per-trader cards** — animated portfolio sparkline (Recharts), P/L %, cash,
  positions, and tabbed Activity / Holdings / Trades.
- **Floor control** — start/stop the background trading floor from the header.
- **Resilient** — clear connecting / disconnected / error states.
- Zero UI framework — a hand-built dark glassmorphism design system in one CSS file.

## 🚀 Getting started

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. In dev, requests to `/api/*` are proxied to the
backend at `http://localhost:8000` (see `vite.config.ts`), so **make sure the
backend is running** first:

```bash
cd ..            # backend lives at the repo root
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## ⚙️ Configuration

Copy `.env.example` to `.env` to override defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | _(empty)_ | Backend origin. Leave empty for the dev proxy; set to `https://your-backend` in production. |
| `VITE_POLL_INTERVAL_MS` | `8000` | Dashboard refresh interval (ms). |
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | Dev-proxy target (build-time, used by `vite.config.ts`). |

## 📦 Build

```bash
npm run build      # type-check + production bundle into dist/
npm run preview    # serve the built bundle locally
```

When deploying, set `VITE_API_BASE_URL` to your backend's public origin and make
sure the backend's `FRONTEND_ORIGINS` env var allows this frontend's origin
(CORS).

## 🗂️ Structure

```
src/
├── api/          # client.ts (fetch wrapper) + types.ts (backend shapes)
├── components/   # TraderCard, PortfolioChart, SummaryBar, FloorControl, …
├── hooks/        # usePolling — interval polling with no-flicker refresh
├── lib/          # format.ts — currency / %, time helpers
├── theme/        # traders.ts — per-trader accent colors & identity
├── App.tsx       # layout, polling orchestration, page states
└── index.css     # design system (tokens + components)
```
