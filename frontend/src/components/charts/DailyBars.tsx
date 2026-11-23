import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";

type Point = { day: string; value: number };

const tick = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });

function Tip({ active, payload, label, format, name }: TooltipContentProps<number, string> & { format: (n: number) => string; name: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-panel px-3 py-2 text-sm shadow-[0_8px_24px_-8px_rgb(0_0_0/0.2)]">
      <p className="text-xs text-ink-3">{tick(String(label))}</p>
      <p className="font-figure text-xl text-ink">{format(Number(payload[0].value))}</p>
      <p className="text-xs text-ink-3">{name}</p>
    </div>
  );
}

/** Single-series daily bars. The hovered day lights up in the accent; the rest stay quiet. */
export function DailyBars({ data, format, label, height = 220 }: { data: Point[]; format: (n: number) => string; label: string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div>
      <div style={{ height }} role="img" aria-label={`${label} per day`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 8, right: 0, left: 0, bottom: 0 }}
            barCategoryGap="22%"
            onMouseMove={(s) => setHover(typeof s.activeTooltipIndex === "number" ? s.activeTooltipIndex : null)}
            onMouseLeave={() => setHover(null)}
          >
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="day" tickFormatter={tick} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={false} tickLine={false} minTickGap={28} dy={6} />
            <YAxis tickFormatter={format} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={false} tickLine={false} width={58} allowDecimals={false} />
            <Tooltip cursor={false} content={(p) => <Tip {...(p as TooltipContentProps<number, string>)} format={format} name={label} />} />
            <Bar dataKey="value" radius={[5, 5, 1, 1]} maxBarSize={26} isAnimationActive={false}>
              {data.map((_, i) => (
                <Cell key={i} fill="var(--series-1)" fillOpacity={hover === null || hover === i ? 1 : 0.28} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-3 text-sm text-ink-3">
        <summary className="cursor-pointer select-none hover:text-ink">View as table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="py-1 font-medium">Day</th>
              <th className="py-1 text-right font-medium">{label}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.day} className="border-t border-line">
                <td className="py-1">{tick(p.day)}</td>
                <td className="py-1 text-right">{format(p.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/** A tiny trend line for a headline figure. Decorative: the figure beside it carries the number. */
export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  if (values.length < 2) return null;
  const w = 120;
  const h = 32;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 2 - ((v - min) / (max - min || 1)) * (h - 4)]);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={className} preserveAspectRatio="none" aria-hidden>
      <path d={`${d} L${w},${h} L0,${h} Z`} fill="var(--accent)" fillOpacity="0.07" />
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r="2.2" fill="var(--accent)" />
    </svg>
  );
}
