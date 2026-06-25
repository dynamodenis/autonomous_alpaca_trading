// TypeScript shapes mirroring the FastAPI backend's JSON payloads.
// Source of truth: backend/api.py + backend/accounts.py.

export interface Transaction {
  symbol: string;
  quantity: number;
  price: number;
  timestamp: string;
  rationale: string;
}

/** A single (timestamp, portfolio-value) point from the time series. */
export type PortfolioPoint = [string, number];

export interface Account {
  name: string;
  balance: number;
  strategy: string;
  /** symbol -> share count */
  holdings: Record<string, number>;
  transactions: Transaction[];
  portfolio_value_time_series: PortfolioPoint[];
  total_portfolio_value: number;
  total_profit_loss: number;
}

/** Roster entry from GET /api/traders. */
export interface Trader {
  name: string;
  lastname: string;
  model: string;
}

export interface LogEntry {
  timestamp: string;
  type: string;
  message: string;
}

/** One element of GET /api/dashboard. */
export interface DashboardTrader extends Trader {
  account: Account;
  logs: LogEntry[];
}

export interface FloorStatus {
  running: boolean;
}

export interface FloorControlResult extends FloorStatus {
  message: string;
}
