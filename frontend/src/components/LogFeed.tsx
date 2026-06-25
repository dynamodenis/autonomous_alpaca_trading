import type { LogEntry } from "../api/types";
import { formatTime } from "../lib/format";

interface Props {
  logs: LogEntry[];
}

// Map a backend log "type" to a CSS modifier class for coloring.
function typeClass(type: string): string {
  const t = type.toLowerCase();
  if (t.includes("error") || t.includes("fail")) return "error";
  if (t.includes("account") || t.includes("trade")) return "account";
  if (t.includes("agent") || t.includes("response")) return "agent";
  return "trace";
}

export default function LogFeed({ logs }: Props) {
  if (!logs || logs.length === 0) {
    return (
      <div className="empty">
        <div className="big">🛰️</div>
        <div>No activity logged yet.</div>
      </div>
    );
  }

  // Backend returns oldest -> newest; show newest first.
  const rows = [...logs].reverse();

  return (
    <div className="logs">
      {rows.map((log, i) => (
        <div className="log-row" key={`${log.timestamp}-${i}`}>
          <span className="log-time">{formatTime(log.timestamp)}</span>
          <span className="log-msg">
            <span className={`log-type ${typeClass(log.type)}`}>
              {log.type}
            </span>
            <span className="log-text">{log.message}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
