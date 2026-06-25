import type { Transaction } from "../api/types";
import { formatUsd, formatTime } from "../lib/format";

interface Props {
  transactions: Transaction[];
}

export default function Transactions({ transactions }: Props) {
  if (!transactions || transactions.length === 0) {
    return (
      <div className="empty">
        <div className="big">📜</div>
        <div>No trades executed yet.</div>
      </div>
    );
  }

  // Newest first.
  const rows = [...transactions].reverse();

  return (
    <div className="tx-list">
      {rows.map((tx, i) => {
        const isBuy = tx.quantity >= 0;
        const value = Math.abs(tx.quantity) * tx.price;
        return (
          <div className="tx-row" key={`${tx.timestamp}-${tx.symbol}-${i}`}>
            <span className={`tx-side ${isBuy ? "tx-buy" : "tx-sell"}`}>
              {isBuy ? "BUY" : "SELL"}
            </span>
            <div className="tx-main">
              <span className="sym">
                {Math.abs(tx.quantity)} {tx.symbol}
              </span>
              <div className="meta" title={tx.rationale}>
                @ {formatUsd(tx.price)} · {formatTime(tx.timestamp)}
              </div>
            </div>
            <span className="tx-amt">{formatUsd(value)}</span>
          </div>
        );
      })}
    </div>
  );
}
