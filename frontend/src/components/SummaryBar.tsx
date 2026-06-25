import type { CSSProperties } from "react";
import type { DashboardTrader } from "../api/types";
import {
  formatSignedPercent,
  formatSignedUsd,
  formatUsd,
  pnlPercent,
} from "../lib/format";
import { traderTheme } from "../theme/traders";

interface Props {
  traders: DashboardTrader[];
}

export default function SummaryBar({ traders }: Props) {
  const totalValue = traders.reduce(
    (sum, t) => sum + t.account.total_portfolio_value,
    0,
  );
  const totalPnl = traders.reduce(
    (sum, t) => sum + t.account.total_profit_loss,
    0,
  );
  const invested = traders.length * 10_000;
  const pct = invested ? (totalPnl / invested) * 100 : 0;
  const up = totalPnl >= 0;

  const leader = traders.reduce<DashboardTrader | null>((best, t) => {
    if (!best) return t;
    return t.account.total_profit_loss > best.account.total_profit_loss
      ? t
      : best;
  }, null);

  const leaderTheme = leader ? traderTheme(leader.name) : null;
  const leaderStyle = leaderTheme
    ? ({ color: leaderTheme.accent } as CSSProperties)
    : undefined;

  return (
    <section className="summary">
      <div className="card summary-card">
        <div className="label">Combined portfolio</div>
        <div className="value mono">{formatUsd(totalValue)}</div>
        <div className="sub muted">across {traders.length} AI traders</div>
      </div>

      <div className="card summary-card">
        <div className="label">Total P / L</div>
        <div className={`value mono ${up ? "pos" : "neg"}`}>
          {formatSignedUsd(totalPnl)}
        </div>
        <div className={`sub ${up ? "pos" : "neg"}`}>
          {formatSignedPercent(pct)} vs. {formatUsd(invested)} seed
        </div>
      </div>

      <div className="card summary-card">
        <div className="label">Top performer</div>
        <div className="value" style={leaderStyle}>
          {leader ? `${leader.name} ${leader.lastname}` : "—"}
        </div>
        <div className="sub muted">
          {leader
            ? `${formatSignedPercent(pnlPercent(leader.account.total_profit_loss))} · ${leader.model}`
            : "no data"}
        </div>
      </div>
    </section>
  );
}
