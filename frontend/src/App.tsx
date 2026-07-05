import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api/client";
import type { DashboardTrader, PortfolioSummary } from "./api/types";
import FloorControl from "./components/FloorControl";
import SummaryBar from "./components/SummaryBar";
import TraderCard from "./components/TraderCard";
import { AlertIcon, RefreshIcon } from "./components/icons";
import { usePolling } from "./hooks/usePolling";
import { relativeTime } from "./lib/format";

const POLL_INTERVAL_MS = Number(
  import.meta.env.VITE_POLL_INTERVAL_MS ?? 600_000,
);

export default function App() {
  const [running, setRunning] = useState(false);
  // Assume open until the status endpoint says otherwise, so a failing
  // market-clock lookup never freezes the dashboard while the floor runs.
  const [marketOpen, setMarketOpen] = useState(true);

  // Only poll the dashboard while trades can actually happen: the floor is
  // running AND the market is open. Otherwise the data can't change.
  // The Alpaca portfolio summary is best-effort — a brokerage hiccup must
  // never blank out the trader cards.
  const fetchDashboard = useCallback(async () => {
    const [traders, portfolio] = await Promise.all([
      api.getDashboard(),
      api.getPortfolio().catch((): PortfolioSummary | null => null),
    ]);
    return { traders, portfolio };
  }, []);
  const {
    data,
    error,
    loading,
    refreshing,
    lastUpdated,
    refresh,
  } = usePolling<{
    traders: DashboardTrader[];
    portfolio: PortfolioSummary | null;
  }>(fetchDashboard, POLL_INTERVAL_MS, running && marketOpen);
  const traders = data?.traders ?? null;
  const portfolio = data?.portfolio ?? null;
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(
    null,
  );

  // Lightweight heartbeat: keeps floor status + market clock in sync so we
  // notice when the floor starts or the market opens and resume polling.
  useEffect(() => {
    let active = true;
    const sync = async () => {
      try {
        const status = await api.getFloorStatus();
        if (!active) return;
        setRunning(status.running);
        if (status.market?.ok) setMarketOpen(status.market.is_open ?? true);
      } catch {
        /* dashboard error banner already covers connectivity */
      }
    };
    sync();
    const id = window.setInterval(sync, POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  // Auto-dismiss toasts.
  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(id);
  }, [toast]);

  const handleFloorChange = useCallback(
    (isRunning: boolean, message: string) => {
      setRunning(isRunning);
      setToast({ kind: "ok", msg: message });
      refresh();
    },
    [refresh],
  );

  const handleFloorInfo = useCallback(
    (message: string) => {
      setToast({ kind: "ok", msg: message });
      refresh();
    },
    [refresh],
  );

  const handleFloorError = useCallback((message: string) => {
    setToast({ kind: "err", msg: message });
  }, []);

  const updatedLabel = useMemo(
    () => (lastUpdated ? relativeTime(new Date(lastUpdated).toISOString()) : "—"),
    [lastUpdated],
  );

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-mark">📈</div>
          <div>
            <h1>AI Trading Floor</h1>
            <p>Autonomous agents · live paper-trading dashboard</p>
          </div>
        </div>
        <div className="header-right">
          <span className="pill" title="Time since last data refresh">
            <span className={`dot ${refreshing ? "live" : "idle"}`} />
            Updated {updatedLabel}
          </span>
          <button
            className="btn btn-icon"
            onClick={refresh}
            title="Refresh now"
            aria-label="Refresh now"
          >
            <RefreshIcon className={refreshing ? "spin" : undefined} />
          </button>
          <FloorControl
            running={running}
            onChange={handleFloorChange}
            onInfo={handleFloorInfo}
            onError={handleFloorError}
          />
        </div>
      </header>

      {toast && (
        <div className={`banner ${toast.kind === "ok" ? "toast-ok" : ""}`}>
          <AlertIcon />
          <span>{toast.msg}</span>
        </div>
      )}

      {error && (
        <div className="banner">
          <AlertIcon />
          <span>
            {error instanceof ApiError
              ? error.message
              : "Something went wrong talking to the backend."}
            {traders ? " Showing last known data." : ""}
          </span>
        </div>
      )}

      {loading && (
        <div className="center-state">
          <div className="inner">
            <div className="loader" />
            <p className="muted">Connecting to the trading floor…</p>
          </div>
        </div>
      )}

      {!loading && error && !traders && (
        <div className="center-state">
          <div className="inner">
            <div style={{ fontSize: 40 }}>🔌</div>
            <p className="muted" style={{ maxWidth: 360 }}>
              Couldn’t reach the backend. Start it with{" "}
              <code className="mono">uvicorn api:app --port 8000</code> and it’ll
              reconnect automatically.
            </p>
            <button className="btn" onClick={refresh}>
              <RefreshIcon /> Retry
            </button>
          </div>
        </div>
      )}

      {traders && (
        <>
          <SummaryBar traders={traders} portfolio={portfolio} />
          <div className="section-title">
            <h2>Traders</h2>
            <span className="count">{traders.length} competing</span>
          </div>
          <div className="grid">
            {traders.map((t) => (
              <TraderCard key={t.name} trader={t} />
            ))}
          </div>
        </>
      )}

      <footer className="footer">
        <span>
          Simulation only · not financial advice · paper-trading via Alpaca
        </span>
        <span>
          <a
            href="https://github.com/dynamodenis/autonomous_alpaca_trading"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>{" "}
          ·{" "}
          <a
            href="https://huggingface.co/spaces/dynamodenis254/alpaca_trading"
            target="_blank"
            rel="noreferrer"
          >
            🤗 Backend
          </a>{" "}
          · Built with React · Vite ·{" "}
          <a
            href="https://www.linkedin.com/in/dynamo-denis-mbugua-53304b197/"
            target="_blank"
            rel="noreferrer"
          >
            DynamoDenis
          </a>
        </span>
      </footer>
    </div>
  );
}
