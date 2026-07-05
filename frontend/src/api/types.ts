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
  market?: MarketInfo;
}

/** Alpaca market clock, as surfaced by GET /api/floor/status and POST /api/floor/start. */
export interface MarketInfo {
  ok: boolean;
  is_open?: boolean;
  next_open?: string | null;
  next_close?: string | null;
  error?: string;
}

export interface BalanceSyncEntry {
  name: string;
  old_balance: number;
  new_balance: number;
}

/** Result of syncing trader balances from the live Alpaca account. */
export interface BalanceSync {
  ok: boolean;
  field?: string;
  alpaca_balance?: number | null;
  synced?: BalanceSyncEntry[];
  error?: string;
}

export interface FloorControlResult extends FloorStatus {
  message: string;
  balance_sync?: BalanceSync;
}

/** Per-symbol holdings drift between summed SQLite holdings and Alpaca. */
export interface HoldingsDrift {
  symbol: string;
  sqlite_total: number;
  alpaca_qty: number;
  diff: number;
}

export interface HoldingsReconcile {
  ok: boolean;
  symbols_checked?: number;
  drift?: HoldingsDrift[];
  error?: string;
}

/** Result of POST /api/reconcile — balances synced + holdings drift report. */
export interface ReconcileResult {
  ok: boolean;
  balances?: BalanceSync;
  holdings?: HoldingsReconcile;
  error?: string;
}
