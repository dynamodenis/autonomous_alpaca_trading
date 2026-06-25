import { useState } from "react";
import type { CSSProperties } from "react";
import type { DashboardTrader } from "../api/types";
import {
  formatNumber,
  formatSignedPercent,
  formatSignedUsd,
  formatUsd,
  formatUsdCompact,
  pnlPercent,
} from "../lib/format";
import { initials, traderTheme } from "../theme/traders";
import Holdings from "./Holdings";
import LogFeed from "./LogFeed";
import PortfolioChart from "./PortfolioChart";
import Transactions from "./Transactions";
import { TrendDownIcon, TrendUpIcon } from "./icons";

type Tab = "activity" | "holdings" | "trades";

interface Props {
  trader: DashboardTrader;
}

export default function TraderCard({ trader }: Props) {
  const [tab, setTab] = useState<Tab>("activity");
  const theme = traderTheme(trader.name);
  const { account } = trader;

  const pnl = account.total_profit_loss;
  const up = pnl >= 0;
  const pct = pnlPercent(pnl);
  const positions = Object.values(account.holdings).filter((q) => q !== 0).length;

  const style = {
    "--accent": theme.accent,
    "--accent-soft": theme.accentSoft,
  } as CSSProperties;

  return (
    <article className="card trader" style={style}>
      <header className="trader-head">
        <div className="avatar">{initials(trader.name, trader.lastname)}</div>
        <div className="trader-id">
          <div className="name">
            {trader.name} {trader.lastname} <span>{theme.emoji}</span>
          </div>
          <div className="tagline">{theme.tagline}</div>
        </div>
        <span className="model-chip">{trader.model}</span>
      </header>

      <div className="trader-value">
        <div>
          <div className="big mono">{formatUsd(account.total_portfolio_value)}</div>
        </div>
        <div className="pnl">
          <span className={`pct ${up ? "pnl-up" : "pnl-down"}`}>
            {up ? <TrendUpIcon width={13} height={13} /> : <TrendDownIcon width={13} height={13} />}
            {formatSignedPercent(pct)}
          </span>
          <div className={`mono ${up ? "pos" : "neg"}`} style={{ marginTop: 4 }}>
            {formatSignedUsd(pnl)}
          </div>
        </div>
      </div>

      <PortfolioChart
        series={account.portfolio_value_time_series}
        accent={theme.accent}
      />

      <div className="trader-stats">
        <div className="cell">
          <div className="k">Cash</div>
          <div className="v mono">{formatUsdCompact(account.balance)}</div>
        </div>
        <div className="cell">
          <div className="k">Positions</div>
          <div className="v mono">{positions}</div>
        </div>
        <div className="cell">
          <div className="k">Trades</div>
          <div className="v mono">{formatNumber(account.transactions.length)}</div>
        </div>
      </div>

      <div className="tabs">
        <button
          className={`tab ${tab === "activity" ? "active" : ""}`}
          onClick={() => setTab("activity")}
        >
          Activity
        </button>
        <button
          className={`tab ${tab === "holdings" ? "active" : ""}`}
          onClick={() => setTab("holdings")}
        >
          Holdings
        </button>
        <button
          className={`tab ${tab === "trades" ? "active" : ""}`}
          onClick={() => setTab("trades")}
        >
          Trades
        </button>
      </div>

      <div className="tab-body">
        {tab === "activity" && <LogFeed logs={trader.logs} />}
        {tab === "holdings" && <Holdings holdings={account.holdings} />}
        {tab === "trades" && <Transactions transactions={account.transactions} />}
      </div>
    </article>
  );
}
