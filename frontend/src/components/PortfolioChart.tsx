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
import { formatUsd, formatDateTime } from "../lib/format";

interface Props {
  series: PortfolioPoint[];
  accent: string;
  baseline?: number;
}

interface Datum {
  t: string;
  v: number;
}

const STARTING_CAPITAL = 10_000;

export default function PortfolioChart({
  series,
  accent,
  baseline = STARTING_CAPITAL,
}: Props) {
  const gradientId = useId();

  if (!series || series.length < 2) {
    return (
      <div className="chart-empty">Awaiting portfolio history…</div>
    );
  }

  const data: Datum[] = series.map(([t, v]) => ({ t, v }));
  const values = data.map((d) => d.v);
  const min = Math.min(...values, baseline);
  const max = Math.max(...values, baseline);
  const pad = (max - min) * 0.12 || max * 0.02 || 1;

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
            y={baseline}
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
                    {formatUsd(d.v)}
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
