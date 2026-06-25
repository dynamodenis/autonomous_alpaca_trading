const STARTING_CAPITAL = 10_000;

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const usdCompact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export const formatUsd = (value: number) => usd.format(value);
export const formatUsdCompact = (value: number) => usdCompact.format(value);

/** Signed currency, e.g. "+$1,204.55" / "-$87.10". */
export function formatSignedUsd(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${usd.format(Math.abs(value))}`;
}

/** P/L as a percentage of the $10,000 starting capital. */
export function pnlPercent(pnl: number): number {
  return (pnl / STARTING_CAPITAL) * 100;
}

export function formatSignedPercent(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

/** Parse the backend's "YYYY-MM-DD HH:MM:SS" stamps as local time. */
export function parseTimestamp(ts: string): Date {
  // Treat the space-separated stamp as local time (no TZ suffix).
  return new Date(ts.replace(" ", "T"));
}

export function formatTime(ts: string): string {
  const d = parseTimestamp(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateTime(ts: string): string {
  const d = parseTimestamp(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "3m ago", "2h ago", "just now". */
export function relativeTime(ts: string, now: number = Date.now()): string {
  const d = parseTimestamp(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const seconds = Math.round((now - d.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}
