import { useState } from "react";
import { api, ApiError } from "../api/client";
import { formatUsd } from "../lib/format";
import { PlayIcon, StopIcon, SyncIcon } from "./icons";

interface Props {
  running: boolean;
  /** Called after a successful start/stop so the dashboard can refresh. */
  onChange: (running: boolean, message: string) => void;
  /** Called for non-state-changing successes (e.g. reconcile) — shows an ok toast. */
  onInfo: (message: string) => void;
  onError: (message: string) => void;
}

/** Format an ISO datetime as a short, human local time, e.g. "Mon, Jun 30, 09:30 AM". */
function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function FloorControl({ running, onChange, onInfo, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const [reconciling, setReconciling] = useState(false);

  async function toggle() {
    setBusy(true);
    try {
      const result = running ? await api.stopFloor() : await api.startFloor();
      let msg = result.message;
      // When starting while the market is closed, spell out when the first run lands.
      const market = result.market;
      if (
        !running &&
        market?.ok &&
        market.is_open === false &&
        market.next_open
      ) {
        msg = `Floor started — market is closed. First run at ${formatWhen(market.next_open)}.`;
      }
      onChange(result.running, msg);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Floor control failed");
    } finally {
      setBusy(false);
    }
  }

  async function reconcile() {
    setReconciling(true);
    try {
      const r = await api.reconcile();
      if (r.balances?.ok) {
        const bal =
          typeof r.balances.alpaca_balance === "number"
            ? formatUsd(r.balances.alpaca_balance)
            : "the Alpaca account";
        const drift = r.holdings?.drift?.length ?? 0;
        const holdingsMsg = !r.holdings?.ok
          ? " (holdings check unavailable)"
          : drift === 0
            ? " Holdings in sync."
            : ` ⚠ ${drift} holding${drift > 1 ? "s" : ""} drifting from Alpaca.`;
        onInfo(`Balances synced from ${bal}.${holdingsMsg}`);
      } else {
        onError(
          `Reconcile failed: ${r.balances?.error ?? r.error ?? "unknown error"}`,
        );
      }
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Reconcile failed");
    } finally {
      setReconciling(false);
    }
  }

  return (
    <>
      <span className="pill">
        <span className={`dot ${running ? "live" : "idle"}`} />
        {running ? "Floor live" : "Floor idle"}
      </span>
      <button
        className="btn"
        onClick={reconcile}
        disabled={reconciling}
        title="Sync trader balances from your live Alpaca account"
      >
        <SyncIcon className={reconciling ? "spin" : undefined} />
        {reconciling ? "Syncing…" : "Reconcile"}
      </button>
      <button
        className={`btn ${running ? "btn-stop" : "btn-start"}`}
        onClick={toggle}
        disabled={busy}
      >
        {running ? <StopIcon /> : <PlayIcon />}
        {busy ? "Working…" : running ? "Stop floor" : "Start floor"}
      </button>
    </>
  );
}
