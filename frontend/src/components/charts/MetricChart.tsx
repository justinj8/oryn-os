import { useId } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";

type Point = { day: string; value: number };
const tick = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });

function Tip({ active, payload, label, format }: TooltipContentProps<number, string> & { format: (n: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="material rounded-lg px-3 py-2 shadow-[var(--pop-shadow)]">
      <p className="text-[11px] text-ink-3">{tick(String(label))}</p>
      <p className="font-figure text-[17px] text-ink">{format(Number(payload[0].value))}</p>
    </div>
  );
}

/** One metric over time: a soft area under a crisp line, with a scrub line that follows the pointer. */
export function MetricChart({ data, format, label, height = 240 }: { data: Point[]; format: (n: number) => string; label: string; height?: number }) {
  const gid = useId().replace(/:/g, "");
  return (
    <div style={{ height }} role="img" aria-label={`${label} per day`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.22} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--line)" strokeOpacity={0.7} />
          <XAxis dataKey="day" tickFormatter={tick} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={36} dy={6} />
          <YAxis tickFormatter={format} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={56} allowDecimals={false} />
          <Tooltip cursor={{ stroke: "var(--ink-3)", strokeWidth: 1, strokeDasharray: "3 3" }} content={(p) => <Tip {...(p as TooltipContentProps<number, string>)} format={format} />} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            fill={`url(#${gid})`}
            activeDot={{ r: 4, fill: "var(--accent)", stroke: "var(--panel)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
