import { useId } from "react";
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import type { PortfolioPoint } from "../api/types";
import { formatSignedUsd, formatDateTime } from "../lib/format";

interface Props {
  /** The trader's profit/loss over time. */
  series: PortfolioPoint[];
  accent: string;
}

interface Datum {
  t: string;
  v: number;
}

// Break-even: the dashed line the P/L curve is read against.
const BASELINE = 0;

export default function PortfolioChart({ series, accent }: Props) {
  const gradientId = useId();

  if (!series || series.length < 2) {
    return (
      <div className="chart-empty">Awaiting P/L history…</div>
    );
  }

  const data: Datum[] = series.map(([t, v]) => ({ t, v }));
  const values = data.map((d) => d.v);
  const min = Math.min(...values, BASELINE);
  const max = Math.max(...values, BASELINE);
  const pad = (max - min) * 0.12 || 1;

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity={0.38} />
              <stop offset="100%" stopColor={accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={[min - pad, max + pad]} />
          <ReferenceLine
            y={BASELINE}
            stroke="rgba(148,163,184,0.35)"
            strokeDasharray="4 4"
          />
          <Tooltip
            cursor={{ stroke: accent, strokeOpacity: 0.4 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as Datum;
              return (
                <div className="rc-tooltip">
                  <div className="t">{formatDateTime(d.t)}</div>
                  <div className="v" style={{ color: accent }}>
                    {formatSignedUsd(d.v)}
                  </div>
                </div>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={accent}
            strokeWidth={2.2}
            fill={`url(#${gradientId})`}
            isAnimationActive={true}
            animationDuration={550}
            dot={false}
            activeDot={{ r: 3.5, fill: accent, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
