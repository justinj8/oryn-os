import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { DailyBars } from "@/components/charts/DailyBars";
import { RunStrip } from "@/components/runs/RunStrip";
import { Empty, ErrorNote, PageHeader, Section, Skeleton, StatusPill, Tag } from "@/components/ui";
import { RangeToggle } from "@/components/ui/RangeToggle";
import { cost, duration, num, pct, usd } from "@/lib/format";

function Figure({ label, value, note, testId }: { label: string; value: ReactNode; note?: ReactNode; testId?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-ink-3">{label}</dt>
      <dd className="mt-0.5 flex items-baseline gap-2">
        <span className="font-display text-[28px] leading-none font-semibold" data-testid={testId}>
          {value}
        </span>
        {note}
      </dd>
    </div>
  );
}

export default function Overview() {
  const { tenant } = useAuth();
  const tid = tenant?.tenant_id;
  const [range, setRange] = useState(30);
  const m = useQuery({ queryKey: ["metrics", "overview", tid, range], queryFn: () => api.get<S["OverviewMetrics"]>("/api/metrics/overview", { range }) });
  const ts = useQuery({ queryKey: ["metrics", "ts", tid, range], queryFn: () => api.get<S["TimeseriesPoint"][]>("/api/metrics/timeseries", { range }) });
  const agents = useQuery({ queryKey: ["metrics", "agents", tid, range], queryFn: () => api.get<S["AgentLeaderboardRow"][]>("/api/metrics/agents", { range }) });
  const runs = useQuery({ queryKey: ["runs", "board", tid], queryFn: () => api.get<S["RunPage"]>("/api/runs", { limit: 12 }) });

  const live = (runs.data?.items ?? []).filter((r) => r.status === "running" || r.status === "waiting_approval");
  const recent = (runs.data?.items ?? []).filter((r) => !live.includes(r)).slice(0, 5);
  const d = m.data;

  return (
    <>
      <PageHeader
        title="Overview"
        sub={`What ${tenant?.name ?? "your business"}'s agents are working on, and what it's worth.`}
        actions={<RangeToggle value={range} onChange={setRange} />}
      />

      <section aria-labelledby="board" className="mb-8">
        <h2 id="board" className="mb-3 font-display text-xl font-semibold">
          In flight {live.length > 0 && <span className="text-ink-3">({live.length})</span>}
        </h2>
        {runs.isLoading ? (
          <Skeleton className="h-16" />
        ) : live.length ? (
          <div className="grid gap-2">
            {live.map((r) => (
              <RunStrip key={r.id} run={r} />
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-line">
            <Empty title="Nothing in flight right now">
              Fire an event from <Link className="text-flight hover:underline" to="/simulators">Simulators</Link> or switch on live
              traffic to watch agents pick up work.
            </Empty>
          </div>
        )}
        {recent.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-sm text-ink-3">Recently finished</h3>
            <div className="grid gap-2">
              {recent.map((r) => (
                <RunStrip key={r.id} run={r} />
              ))}
            </div>
          </div>
        )}
      </section>

      <ErrorNote error={m.error} />
      {d && (
        <>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 border-y border-line py-5 sm:grid-cols-3 lg:grid-cols-5">
            <Figure label="Completion rate" value={pct(d.completion_rate)} />
            <Figure label="Runs" value={num(d.runs_total)} note={d.in_flight ? <span className="text-sm text-ink-3">{d.in_flight} live</span> : null} />
            <Figure label="Typical run (p95)" value={duration(d.p95_duration_s)} />
            <Figure label="Model cost" value={cost(d.llm_cost_usd)} note={d.simulated_cost ? <Tag>Simulated</Tag> : null} />
            <Figure
              label="Waiting for approval"
              value={num(d.approvals_pending)}
              note={d.approvals_pending ? <Link to="/approvals" className="text-sm text-flight hover:underline">Review</Link> : null}
            />
          </dl>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 border-b border-line py-5 sm:grid-cols-3 lg:grid-cols-6">
            <Figure label="Meetings booked" value={num(d.meetings_booked)} />
            <Figure label="Pipeline created" value={usd(d.pipeline_usd)} />
            <Figure label="Tickets resolved" value={num(d.tickets_resolved)} />
            <Figure label="Hours saved" value={num(Math.round(d.minutes_saved / 60))} />
            <Figure label="Labor saved" value={usd(d.labor_savings_usd)} note={<span className="text-xs text-ink-3">at {usd(d.hourly_rate_usd)}/h</span>} />
            <Figure label="Return on model cost" value={d.roi_multiple ? `${Math.round(d.roi_multiple).toLocaleString()}×` : "—"} testId="roi" />
          </dl>
        </>
      )}

      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <Section title="Runs per day">
          {ts.data ? <DailyBars label="Runs" data={ts.data.map((p) => ({ day: p.day, value: p.runs }))} format={(n) => num(n)} /> : <Skeleton className="h-52" />}
        </Section>
        <Section title="Outcome value per day">
          {ts.data ? (
            <DailyBars label="Outcome value" data={ts.data.map((p) => ({ day: p.day, value: p.outcomes_value_usd }))} format={(n) => usd(n)} />
          ) : (
            <Skeleton className="h-52" />
          )}
        </Section>
      </div>

      <Section title="Agents" className="mt-4">
        {agents.data?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-ink-3">
                <tr>
                  <th className="py-1.5 font-normal">Agent</th>
                  <th className="py-1.5 text-right font-normal">Runs</th>
                  <th className="py-1.5 text-right font-normal">Completion</th>
                  <th className="py-1.5 text-right font-normal">Model calls per step</th>
                  <th className="py-1.5 text-right font-normal">Cost</th>
                </tr>
              </thead>
              <tbody>
                {agents.data.map((a) => (
                  <tr key={a.agent_id} className="border-t border-line">
                    <td className="py-2">
                      <span className="font-medium">{a.name}</span>
                      {a.name.toLowerCase() !== a.role && <span className="ml-1.5 text-ink-3 capitalize">{a.role}</span>}
                    </td>
                    <td className="py-2 text-right">{num(a.runs)}</td>
                    <td className="py-2 text-right">{pct(a.completion_rate)}</td>
                    <td className="py-2 text-right">{a.avg_llm_calls?.toFixed(1) ?? "—"}</td>
                    <td className="py-2 text-right">{cost(a.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No agent activity in this range" />
        )}
      </Section>
      <span hidden>
        <StatusPill status="running" />
      </span>
    </>
  );
}
