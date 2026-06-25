import type {
  DashboardTrader,
  FloorControlResult,
  FloorStatus,
  LogEntry,
  Trader,
} from "./types";

// In dev, VITE_API_BASE_URL is empty and requests hit "/api/*", which Vite's
// proxy forwards to the backend (no CORS). In prod, set it to the backend origin.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(
      "Could not reach the backend. Is it running on port 8000?",
    );
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(detail, res.status);
  }

  return (await res.json()) as T;
}

export const api = {
  getDashboard: (logLimit = 13) =>
    request<DashboardTrader[]>(`/api/dashboard?log_limit=${logLimit}`),

  getTraders: () => request<Trader[]>("/api/traders"),

  getTraderLogs: (name: string, limit = 13) =>
    request<LogEntry[]>(
      `/api/traders/${encodeURIComponent(name)}/logs?limit=${limit}`,
    ),

  getFloorStatus: () => request<FloorStatus>("/api/floor/status"),

  startFloor: () =>
    request<FloorControlResult>("/api/floor/start", { method: "POST" }),

  stopFloor: () =>
    request<FloorControlResult>("/api/floor/stop", { method: "POST" }),
};
