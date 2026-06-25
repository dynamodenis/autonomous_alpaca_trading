import { useState } from "react";
import { api, ApiError } from "../api/client";
import { PlayIcon, StopIcon } from "./icons";

interface Props {
  running: boolean;
  /** Called after a successful start/stop so the dashboard can refresh. */
  onChange: (running: boolean, message: string) => void;
  onError: (message: string) => void;
}

export default function FloorControl({ running, onChange, onError }: Props) {
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    try {
      const result = running ? await api.stopFloor() : await api.startFloor();
      onChange(result.running, result.message);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Floor control failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <span className="pill">
        <span className={`dot ${running ? "live" : "idle"}`} />
        {running ? "Floor live" : "Floor idle"}
      </span>
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
