import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Point = { day: string; value: number };

/** Single-series daily bars. The section title names the series, so there is no legend. */
export function DailyBars({ data, format, label }: { data: Point[]; format: (n: number) => string; label: string }) {
  const tick = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return (
    <div>
      <div className="h-52" role="img" aria-label={`${label} per day`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="var(--line)" strokeOpacity={0.6} />
            <XAxis dataKey="day" tickFormatter={tick} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={false} tickLine={false} minTickGap={24} />
            <YAxis tickFormatter={format} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={false} tickLine={false} width={56} allowDecimals={false} />
            <Tooltip
              cursor={{ fill: "var(--line)", fillOpacity: 0.4 }}
              contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 6, color: "var(--ink)" }}
              labelFormatter={(d) => tick(String(d))}
              formatter={(v) => [format(Number(v)), label]}
            />
            <Bar dataKey="value" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-sm text-ink-3">
        <summary className="cursor-pointer">View as table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="font-medium">Day</th>
              <th className="text-right font-medium">{label}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.day}>
                <td>{tick(p.day)}</td>
                <td className="text-right">{format(p.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
