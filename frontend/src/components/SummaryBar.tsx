import type { CSSProperties } from "react";
import type { DashboardTrader, PortfolioSummary } from "../api/types";
import { formatSignedPercent, formatSignedUsd, formatUsd } from "../lib/format";
import { traderTheme } from "../theme/traders";

interface Props {
  traders: DashboardTrader[];
  /** Live view of the single shared Alpaca account (null while unavailable). */
  portfolio: PortfolioSummary | null;
}

/** A trader's unrealized return on the capital they actually put into positions. */
function traderReturnPct(t: DashboardTrader): number | null {
  const pnl = t.account.total_profit_loss;
  const costBasis = t.account.total_portfolio_value - t.account.balance - pnl;
  return costBasis > 0 ? (pnl / costBasis) * 100 : null;
}

export default function SummaryBar({ traders, portfolio }: Props) {
  // All four traders share ONE Alpaca account, so the combined view comes
  // from the live account snapshot — never from summing the trader cards.
  const live = portfolio?.ok ? portfolio : null;
  const initial = portfolio?.initial_equity ?? null;
  const pnl = live?.pnl;
  const up = (pnl ?? 0) >= 0;

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
  const leaderPct = leader ? traderReturnPct(leader) : null;

  return (
    <section className="summary">
      <div className="card summary-card">
        <div className="label">Initial portfolio</div>
        <div className="value mono">
          {initial != null ? formatUsd(initial) : "—"}
        </div>
        <div className="sub muted">
          {portfolio?.initial_recorded_at
            ? `account value on ${new Date(portfolio.initial_recorded_at).toLocaleDateString()}`
            : "before trading began"}
        </div>
      </div>

      <div className="card summary-card">
        <div className="label">Current portfolio</div>
        <div className="value mono">{live ? formatUsd(live.equity!) : "—"}</div>
        <div className="sub muted">
          {live
            ? `${formatUsd(live.cash ?? 0)} cash · ${formatUsd(live.positions_value ?? 0)} in ${live.positions_count ?? 0} positions`
            : "Alpaca unavailable — retrying"}
        </div>
      </div>

      <div className="card summary-card">
        <div className="label">Total P / L</div>
        <div className={`value mono ${up ? "pos" : "neg"}`}>
          {pnl != null ? formatSignedUsd(pnl) : "—"}
        </div>
        <div className={`sub ${up ? "pos" : "neg"}`}>
          {pnl != null && live?.pnl_pct != null
            ? `${formatSignedPercent(live.pnl_pct)} on the shared account`
            : "since the initial snapshot"}
        </div>
      </div>

      <div className="card summary-card">
        <div className="label">Top performer</div>
        <div className="value" style={leaderStyle}>
          {leader ? `${leader.name} ${leader.lastname}` : "—"}
        </div>
        <div className="sub muted">
          {leader
            ? `${formatSignedUsd(leader.account.total_profit_loss)}${
                leaderPct != null ? ` · ${formatSignedPercent(leaderPct)}` : ""
              } · ${leader.model}`
            : "no data"}
        </div>
      </div>
    </section>
  );
}
