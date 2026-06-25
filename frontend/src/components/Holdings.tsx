import { formatNumber } from "../lib/format";

interface Props {
  holdings: Record<string, number>;
}

export default function Holdings({ holdings }: Props) {
  const rows = Object.entries(holdings)
    .filter(([, qty]) => qty !== 0)
    .sort((a, b) => b[1] - a[1]);

  if (rows.length === 0) {
    return (
      <div className="empty">
        <div className="big">💵</div>
        <div>All cash — no open positions yet.</div>
      </div>
    );
  }

  const max = Math.max(...rows.map(([, q]) => q));

  return (
    <div className="holdings">
      {rows.map(([symbol, qty]) => (
        <div className="holding-row" key={symbol}>
          <span className="sym">{symbol}</span>
          <div className="holding-bar">
            <span style={{ width: `${Math.max((qty / max) * 100, 6)}%` }} />
          </div>
          <span className="qty">{formatNumber(qty)} sh</span>
        </div>
      ))}
    </div>
  );
}
