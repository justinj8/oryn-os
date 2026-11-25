import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Hand, Zap } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { MetricChart } from "@/components/charts/MetricChart";
import { ActivityList, useActivity } from "@/components/chrome/Popovers";
import { RunRoute } from "@/components/runs/RouteBoard";
import { Button, cx, DeltaText, Empty, ErrorNote, PageHeader, Segmented, Skeleton, StatusDot, Tag, type Delta } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { useNow } from "@/hooks/useNow";
import { changeOf, pointsOf } from "@/lib/deltas";
import { cost, duration, num, pct, usd } from "@/lib/format";
import { PRESETS } from "@/lib/presets";

type Metric = "value" | "runs" | "completion" | "cost";

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 5 ? "Working late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

const B = ({ children }: { children: ReactNode }) => <span className="font-semibold text-ink">{children}</span>;

/** A tab that is also a figure: label, value and its change. Picking it puts its series in the chart. */
function MetricTab({ on, label, value, delta, note, onClick, testId }: { on: boolean; label: string; value: ReactNode; delta?: Delta | null; note?: ReactNode; onClick: () => void; testId?: string }) {
  return (
    <button
      role="tab"
      aria-selected={on}
      onClick={onClick}
      className={cx("relative min-w-0 px-5 py-4 text-left transition-colors", on ? "bg-pane" : "hover:bg-fill")}
    >
      {on && <span className="absolute inset-x-5 top-0 h-[2px] rounded-full bg-accent" aria-hidden />}
      <p className={cx("text-[12px]", on ? "font-semibold text-ink" : "text-ink-3")}>{label}</p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="font-figure text-[26px] text-ink" data-testid={testId}>
          {value}
        </span>
        {note}
      </p>
      {delta ? <DeltaText delta={delta} className="mt-0.5 text-[12px]" /> : <p className="mt-0.5 text-[12px] text-ink-3">No earlier period</p>}
    </button>
  );
}

function LiveRun({ run }: { run: S["RunOut"] }) {
  const now = useNow(1000);
  return (
    <Link to={`/runs/${run.id}`} className="block rounded-lg px-3 py-2.5 hover:bg-fill">
      <div className="flex items-baseline gap-2">
        <StatusDot status={run.status} className="translate-y-[-1px]" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{run.title || "Untitled run"}</span>
        <span className="shrink-0 text-[11.5px] text-ink-3 tabular-nums">{duration((now - new Date(run.started_at).getTime()) / 1000)}</span>
      </div>
      <div className="mt-1.5 pl-4">
        <RunRoute run={run} />
      </div>
    </Link>
  );
}

function Panel({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="card flex min-w-0 flex-col">
      <div className="flex items-center justify-between px-4 pt-3.5 pb-1.5">
        <h2 className="text-[13px] font-semibold">{title}</h2>
        {aside && <span className="text-[12px]">{aside}</span>}
      </div>
      <div className="min-h-0 flex-1 px-1 pb-1.5">{children}</div>
    </section>
  );
}

export default function Overview() {
  const { tenant, user, can } = useAuth();
  const tid = tenant?.tenant_id;
  const toast = useToast();
  const qc = useQueryClient();
  const [range, setRange] = useState(30);
  const [metric, setMetric] = useState<Metric>("value");
  const m = useQuery({ queryKey: ["metrics", "overview", tid, range], queryFn: () => api.get<S["OverviewMetrics"]>("/api/metrics/overview", { range }) });
  const ts = useQuery({ queryKey: ["metrics", "ts", tid, range], queryFn: () => api.get<S["TimeseriesPoint"][]>("/api/metrics/timeseries", { range }) });
  const agents = useQuery({ queryKey: ["metrics", "agents", tid, range], queryFn: () => api.get<S["AgentLeaderboardRow"][]>("/api/metrics/agents", { range }) });
  const runs = useQuery({ queryKey: ["runs", "board", tid], queryFn: () => api.get<S["RunPage"]>("/api/runs", { limit: 12 }) });
  const pending = useQuery({ queryKey: ["approvals", "pending", tid], queryFn: () => api.get<S["ApprovalOut"][]>("/api/approvals", { status: "pending" }) });
  const activity = useActivity(8);
  const fire = useMutation({
    mutationFn: () => api.post<S["IngestOut"]>("/api/simulate/events", { type: PRESETS[0].type, payload: PRESETS[0].payload() }),
    onSuccess: (r) => {
      toast(r.run_ids.length ? "Sent a test lead. Watch it under Running now." : "Event received, but no workflow listens for it");
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const d = m.data;
  const p = d?.previous ?? null;
  const points = ts.data ?? [];
  const live = (runs.data?.items ?? []).filter((r) => r.status === "running" || r.status === "waiting_approval");
  const waiting = pending.data ?? [];
  const first = user?.name?.split(" ")[0];
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const series: Record<Metric, { label: string; data: { day: string; value: number }[]; format: (n: number) => string }> = {
    value: { label: "Outcome value", data: points.map((x) => ({ day: x.day, value: x.outcomes_value_usd })), format: (n) => usd(n) },
    runs: { label: "Runs", data: points.map((x) => ({ day: x.day, value: x.runs })), format: (n) => num(n) },
    completion: { label: "Completion rate", data: points.map((x) => ({ day: x.day, value: x.runs ? x.completed / x.runs : 0 })), format: (n) => `${Math.round(n * 100)}%` },
    cost: { label: "Model cost", data: points.map((x) => ({ day: x.day, value: x.cost_usd })), format: (n) => cost(n) },
  };

  return (
    <>
      <PageHeader
        title="Overview"
        actions={
          <Segmented
            label="Time range"
            value={range}
            onChange={setRange}
            options={[7, 30, 90].map((n) => ({ value: n, label: `${n}d` }))}
          />
        }
      />

      <div className="mx-auto max-w-[1180px]">
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-[46rem]">
            <p className="text-[12px] font-semibold text-ink-3">{today}</p>
            <p className="mt-2 text-[26px] leading-[1.25] font-semibold tracking-[-0.022em] text-balance">
              {greeting()}
              {first ? `, ${first}.` : "."}{" "}
              {d ? (
                <span className="font-normal text-ink-3">
                  In the last {range} days your agents booked <B>{num(d.meetings_booked)} meetings</B>, created <B>{usd(d.pipeline_usd)}</B> in pipeline and saved{" "}
                  <B>{num(Math.round(d.minutes_saved / 60))} hours</B> of work.
                </span>
              ) : (
                <span className="font-normal text-ink-3">Gathering the numbers…</span>
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {waiting.length > 0 && (
              <Link to="/approvals" className="flex items-center gap-2 rounded-full bg-hold/12 py-1.5 pr-3 pl-1.5 text-[13px] font-medium text-hold hover:bg-hold/18">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-hold text-white">
                  <Hand size={11} aria-hidden />
                </span>
                {waiting.length} waiting on you
              </Link>
            )}
            <span className="flex items-center gap-2 rounded-full bg-fill px-3 py-1.5 text-[13px] text-ink-2">
              <span className={cx("h-2 w-2 rounded-full", live.length ? "beacon bg-accent" : "bg-idle")} aria-hidden />
              {live.length ? `${live.length} running` : "Nothing running"}
            </span>
          </div>
        </header>

        <ErrorNote error={m.error} />
        <section className="card mt-7 overflow-hidden">
          {d ? (
            <div role="tablist" aria-label="Metric" className="grid grid-cols-2 divide-x divide-line/70 border-b border-line/70 lg:grid-cols-4">
              <MetricTab on={metric === "value"} onClick={() => setMetric("value")} label="Outcome value" value={usd(d.outcomes_value_usd ?? 0)} delta={changeOf(d.outcomes_value_usd, p?.outcomes_value_usd, range)} />
              <MetricTab on={metric === "runs"} onClick={() => setMetric("runs")} label="Runs" value={num(d.runs_total)} delta={changeOf(d.runs_total, p?.runs_total, range, "none")} />
              <MetricTab
                on={metric === "completion"}
                onClick={() => setMetric("completion")}
                label="Completion rate"
                value={pct(d.completion_rate)}
                delta={pointsOf(d.completion_rate, p?.completion_rate, range)}
              />
              <MetricTab on={metric === "cost"} onClick={() => setMetric("cost")} label="Model cost" value={cost(d.llm_cost_usd)} delta={changeOf(d.llm_cost_usd, p?.llm_cost_usd, range, "none")} />
            </div>
          ) : (
            <Skeleton className="m-4 h-20" />
          )}
          <div className="bg-pane px-3 pt-3 pb-2">
            {ts.data ? <MetricChart key={metric} label={series[metric].label} data={series[metric].data} format={series[metric].format} /> : <Skeleton className="h-60" />}
          </div>
        </section>

        <div className="mt-5 grid gap-5 lg:grid-cols-3">
          <Panel
            title="Needs you"
            aside={
              <Link to="/approvals" className="text-accent hover:underline">
                Approvals
              </Link>
            }
          >
            {waiting.length ? (
              <ul>
                {waiting.slice(0, 5).map((a) => {
                  const args = a.action_args as Record<string, unknown>;
                  const amount = args.amount_usd !== undefined ? usd(Number(args.amount_usd), 2) : args.discount_pct !== undefined ? `${args.discount_pct}% off` : null;
                  return (
                    <li key={a.id}>
                      <Link to={`/approvals/${a.id}`} className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-fill">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-hold text-white">
                          <Hand size={13} aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-semibold">{a.description}</span>
                          <span className="block truncate text-[12px] text-ink-3">{a.run_title}</span>
                        </span>
                        {amount && <span className="font-figure text-[14px]">{amount}</span>}
                        <ChevronRight size={14} className="shrink-0 text-ink-3" aria-hidden />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="px-3 py-6 text-center text-[13px] text-ink-3">Nothing is waiting on a decision.</p>
            )}
          </Panel>

          <Panel
            title="Running now"
            aside={
              <Link to="/runs" className="text-accent hover:underline">
                All runs
              </Link>
            }
          >
            {runs.isLoading ? (
              <Skeleton className="m-3 h-24" />
            ) : live.length ? (
              <div>
                {live.slice(0, 4).map((r) => (
                  <LiveRun key={r.id} run={r} />
                ))}
              </div>
            ) : (
              <Empty
                title="Nothing in flight right now"
                action={
                  can("operator") && (
                    <Button size="sm" variant="primary" onClick={() => fire.mutate()} disabled={fire.isPending}>
                      <Zap size={13} aria-hidden /> Send a test lead
                    </Button>
                  )
                }
              >
                <span className="text-[13px]">Fire an event and watch an agent pick it up and hand off.</span>
              </Empty>
            )}
          </Panel>

          <Panel title="Activity">
            {activity.data?.length ? (
              <ActivityList items={activity.data.slice(0, 5)} />
            ) : activity.isLoading ? (
              <Skeleton className="m-3 h-24" />
            ) : (
              <p className="px-3 py-6 text-center text-[13px] text-ink-3">Failures, approvals and outcomes will show up here.</p>
            )}
          </Panel>
        </div>

        {d && (
          <section className="card mt-5 grid grid-cols-2 gap-px overflow-hidden bg-line/70 sm:grid-cols-3 lg:grid-cols-6">
            {(
              [
                ["Hours saved", num(Math.round(d.minutes_saved / 60)), `${usd(d.labor_savings_usd)} of work`],
                ["Meetings booked", num(d.meetings_booked), null],
                ["Tickets resolved", num(d.tickets_resolved), null],
                ["Typical run (p95)", duration(d.p95_duration_s), null],
                ["Waiting for approval", num(d.approvals_pending), d.in_flight ? `${d.in_flight} live` : null],
              ] as [string, string, string | null][]
            ).map(([label, value, note]) => (
              <div key={label} className="bg-group px-4 py-3.5">
                <p className="text-[11.5px] text-ink-3">{label}</p>
                <p className="mt-1 font-figure text-[20px]">{value}</p>
                {note && <p className="text-[11.5px] text-ink-3">{note}</p>}
              </div>
            ))}
            <div className="bg-group px-4 py-3.5">
              <p className="text-[11.5px] text-ink-3">Return on model cost</p>
              <p className="mt-1 flex items-baseline gap-1.5">
                <span className="font-figure text-[20px]" data-testid="roi">
                  {d.roi_multiple ? `${Math.round(d.roi_multiple).toLocaleString()}×` : "—"}
                </span>
                {d.simulated_cost && <Tag>Simulated</Tag>}
              </p>
            </div>
          </section>
        )}

        <section className="card mt-5 overflow-hidden">
          <div className="flex items-center justify-between px-4 pt-3.5 pb-2">
            <h2 className="text-[13px] font-semibold">Agents</h2>
            <Link to="/agents" className="text-[12px] text-accent hover:underline">
              Manage
            </Link>
          </div>
          {agents.data?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="text-left text-[11.5px] text-ink-3">
                  <tr>
                    <th className="px-4 py-1.5 font-normal">Agent</th>
                    <th className="px-4 py-1.5 text-right font-normal">Runs</th>
                    <th className="px-4 py-1.5 font-normal">Completion</th>
                    <th className="hidden px-4 py-1.5 text-right font-normal sm:table-cell">Model calls per step</th>
                    <th className="px-4 py-1.5 text-right font-normal">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.data.map((a) => (
                    <tr key={a.agent_id} className="border-t border-line/70">
                      <td className="px-4 py-2.5">
                        <span className="font-medium">{a.name}</span>
                        {a.name.toLowerCase() !== a.role && <span className="ml-2 text-ink-3 capitalize">{a.role}</span>}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{num(a.runs)}</td>
                      <td className="px-4 py-2.5">
                        <span className="flex items-center gap-2.5">
                          <span className="h-1 w-20 overflow-hidden rounded-full bg-fill-2" aria-hidden>
                            <span className="block h-full rounded-full bg-clear" style={{ width: `${Math.round((a.completion_rate ?? 0) * 100)}%` }} />
                          </span>
                          <span className="tabular-nums">{a.completion_rate === null ? "—" : `${Math.round(a.completion_rate * 100)}%`}</span>
                        </span>
                      </td>
                      <td className="hidden px-4 py-2.5 text-right tabular-nums sm:table-cell">{a.avg_llm_calls?.toFixed(1) ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{cost(a.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No agent activity in this range" />
          )}
        </section>
      </div>
    </>
  );
}
