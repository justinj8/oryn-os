import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Clock, DollarSign, Gauge, Hand, Sparkles, Zap, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { DailyBars, Sparkline } from "@/components/charts/DailyBars";
import { ActivityList, useActivity } from "@/components/chrome/Popovers";
import { RouteRow } from "@/components/runs/RouteBoard";
import { Button, cx, DeltaText, Empty, ErrorNote, Figure, PageHeader, Section, Segmented, Skeleton, Tag, type Delta } from "@/components/ui";
import { RangeToggle } from "@/components/ui/RangeToggle";
import { useToast } from "@/components/ui/toast";
import { changeOf, pointsOf } from "@/lib/deltas";
import { cost, duration, num, pct, usd } from "@/lib/format";
import { PRESETS } from "@/lib/presets";

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 5 ? "Working late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** A highlight tile, the way Apple Health presents a metric: tinted label, big rounded number, what changed. */
function Highlight({
  icon: Icon,
  tint,
  label,
  value,
  note,
  delta,
  trend,
  testId,
}: {
  icon: LucideIcon;
  tint: string;
  label: string;
  value: ReactNode;
  note?: ReactNode;
  delta?: Delta | null;
  trend?: number[];
  testId?: string;
}) {
  return (
    <div className="card flex min-w-0 flex-col p-5">
      <p className={cx("flex items-center gap-1.5 text-[14px] font-semibold", tint)}>
        <Icon size={15} strokeWidth={2.4} aria-hidden />
        {label}
      </p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="font-figure text-[34px] text-ink" data-testid={testId}>
              {value}
            </span>
            {note && <span className="text-[13px] text-ink-3">{note}</span>}
          </p>
          {delta ? <DeltaText delta={delta} className="mt-1" /> : <p className="mt-1 text-[13px] text-transparent select-none">.</p>}
        </div>
        {trend && <Sparkline values={trend} className="h-9 w-24 shrink-0" />}
      </div>
    </div>
  );
}

export default function Overview() {
  const { tenant, user, can } = useAuth();
  const tid = tenant?.tenant_id;
  const toast = useToast();
  const qc = useQueryClient();
  const [range, setRange] = useState(30);
  const [series, setSeries] = useState<"runs" | "value">("runs");
  const m = useQuery({ queryKey: ["metrics", "overview", tid, range], queryFn: () => api.get<S["OverviewMetrics"]>("/api/metrics/overview", { range }) });
  const ts = useQuery({ queryKey: ["metrics", "ts", tid, range], queryFn: () => api.get<S["TimeseriesPoint"][]>("/api/metrics/timeseries", { range }) });
  const agents = useQuery({ queryKey: ["metrics", "agents", tid, range], queryFn: () => api.get<S["AgentLeaderboardRow"][]>("/api/metrics/agents", { range }) });
  const runs = useQuery({ queryKey: ["runs", "board", tid], queryFn: () => api.get<S["RunPage"]>("/api/runs", { limit: 12 }) });
  const activity = useActivity(8);
  const fire = useMutation({
    mutationFn: () => api.post<S["IngestOut"]>("/api/simulate/events", { type: PRESETS[0].type, payload: PRESETS[0].payload() }),
    onSuccess: (r) => {
      toast(r.run_ids.length ? "Sent a test lead. Watch it travel below." : "Event received, but no workflow listens for it");
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const items = runs.data?.items ?? [];
  const live = items.filter((r) => r.status === "running" || r.status === "waiting_approval");
  const recent = items.filter((r) => !live.includes(r)).slice(0, 4);
  const d = m.data;
  const p = d?.previous ?? null;
  const points = ts.data ?? [];
  const first = user?.name?.split(" ")[0];
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

  return (
    <>
      <p className="text-[13px] font-semibold text-ink-3">{today}</p>
      <PageHeader
        title="Overview"
        sub={`${greeting()}${first ? `, ${first}` : ""}. Here is what ${tenant?.name ?? "your business"}'s agents did in the last ${range} days.`}
        actions={<RangeToggle value={range} onChange={setRange} />}
      />

      {!!d?.approvals_pending && (
        <Link to="/approvals" className="card group mb-6 flex items-center gap-3.5 px-5 py-4 transition-transform active:scale-[0.995]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-hold text-white">
            <Hand size={17} aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold">
              {d.approvals_pending} {d.approvals_pending === 1 ? "decision is" : "decisions are"} waiting on your team
            </span>
            <span className="block text-[13px] text-ink-3">Agents stay paused until someone approves or rejects.</span>
          </span>
          <span className="flex items-center text-[14px] font-medium text-accent">
            Review <ChevronRight size={16} className="transition-transform group-hover:translate-x-0.5" aria-hidden />
          </span>
        </Link>
      )}

      <ErrorNote error={m.error} />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {d ? (
          <>
            <Highlight
              icon={Sparkles}
              tint="text-accent"
              label="Outcome value"
              value={usd(d.outcomes_value_usd ?? points.reduce((s, x) => s + x.outcomes_value_usd, 0))}
              delta={changeOf(d.outcomes_value_usd, p?.outcomes_value_usd, range)}
              trend={points.map((x) => x.outcomes_value_usd)}
            />
            <Highlight
              icon={Clock}
              tint="text-hold"
              label="Hours saved"
              value={num(Math.round(d.minutes_saved / 60))}
              note={`${usd(d.labor_savings_usd)} of work`}
              delta={changeOf(d.minutes_saved, p?.minutes_saved, range)}
            />
            <Highlight
              icon={Gauge}
              tint="text-clear"
              label="Completion rate"
              value={pct(d.completion_rate)}
              note={`of ${num(d.runs_total)} runs`}
              delta={pointsOf(d.completion_rate, p?.completion_rate, range)}
              trend={points.map((x) => x.runs)}
            />
            <Highlight
              icon={DollarSign}
              tint="text-divert"
              label="Return on model cost"
              value={d.roi_multiple ? `${Math.round(d.roi_multiple).toLocaleString()}×` : "—"}
              testId="roi"
              note={d.simulated_cost ? <Tag>Simulated</Tag> : null}
              delta={changeOf(d.roi_multiple, p?.roi_multiple, range)}
            />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[136px]" />)
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Section
          flush
          title={
            <span className="flex items-center gap-2">
              In flight
              {live.length > 0 && <span className="rounded-full bg-accent px-2 py-px text-[12px] font-semibold text-white">{live.length}</span>}
            </span>
          }
          aside={
            <Link to="/runs" className="text-accent hover:underline">
              See all
            </Link>
          }
        >
          {runs.isLoading ? (
            <div className="p-5">
              <Skeleton className="h-16" />
            </div>
          ) : live.length ? (
            <div className="mt-1 divide-y divide-line/70">
              {live.map((r) => (
                <RouteRow key={r.id} run={r} />
              ))}
            </div>
          ) : (
            <Empty
              title="Nothing in flight right now"
              action={
                can("operator") && (
                  <Button variant="primary" onClick={() => fire.mutate()} disabled={fire.isPending}>
                    <Zap size={15} aria-hidden /> Send a test lead
                  </Button>
                )
              }
            >
              Fire an event and watch an agent pick it up, ask for approval and hand off. More scenarios are in{" "}
              <Link className="text-accent hover:underline" to="/simulators">
                Simulators
              </Link>
              .
            </Empty>
          )}
          {recent.length > 0 && (
            <>
              <p className="px-5 pt-4 pb-1 text-[13px] font-semibold text-ink-3">Recently finished</p>
              <div className="divide-y divide-line/70 pb-1">
                {recent.map((r) => (
                  <RouteRow key={r.id} run={r} />
                ))}
              </div>
            </>
          )}
        </Section>

        <Section flush title="Recent activity">
          {activity.data?.length ? (
            <div className="mt-1 pb-1">
              <ActivityList items={activity.data} />
            </div>
          ) : activity.isLoading ? (
            <div className="p-5">
              <Skeleton className="h-40" />
            </div>
          ) : (
            <Empty title="All quiet">Failures, approvals and outcomes will show up here.</Empty>
          )}
        </Section>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Section
          title={series === "runs" ? "Runs per day" : "Outcome value per day"}
          aside={
            <Segmented
              label="Series"
              value={series}
              onChange={setSeries}
              options={[
                { value: "runs", label: "Runs" },
                { value: "value", label: "Value" },
              ]}
            />
          }
        >
          {ts.data ? (
            series === "runs" ? (
              <DailyBars label="Runs" data={points.map((x) => ({ day: x.day, value: x.runs }))} format={(n) => num(n)} />
            ) : (
              <DailyBars label="Outcome value" data={points.map((x) => ({ day: x.day, value: x.outcomes_value_usd }))} format={(n) => usd(n)} />
            )
          ) : (
            <Skeleton className="h-56" />
          )}
        </Section>

        <Section title="Operations">
          {d ? (
            <dl className="grid grid-cols-2 gap-x-5 gap-y-6 pt-1">
              <Figure label="Meetings booked" value={num(d.meetings_booked)} delta={changeOf(d.meetings_booked, p?.meetings_booked, range)} />
              <Figure label="Pipeline created" value={usd(d.pipeline_usd)} delta={changeOf(d.pipeline_usd, p?.pipeline_usd, range)} />
              <Figure label="Tickets resolved" value={num(d.tickets_resolved)} delta={changeOf(d.tickets_resolved, p?.tickets_resolved, range)} />
              <Figure label="Typical run (p95)" value={duration(d.p95_duration_s)} delta={changeOf(d.p95_duration_s, p?.p95_duration_s, range, "down")} />
              <Figure label="Model cost" value={cost(d.llm_cost_usd)} delta={changeOf(d.llm_cost_usd, p?.llm_cost_usd, range, "none")} />
              <Figure label="Waiting for approval" value={num(d.approvals_pending)} note={d.in_flight ? `${d.in_flight} live` : null} />
            </dl>
          ) : (
            <Skeleton className="h-56" />
          )}
        </Section>
      </div>

      <Section
        title="Agents"
        aside={
          <Link to="/agents" className="text-accent hover:underline">
            Manage
          </Link>
        }
        className="mt-4"
        flush
      >
        {agents.data?.length ? (
          <div className="overflow-x-auto pb-1">
            <table className="w-full text-[14px]">
              <thead className="text-left text-[13px] text-ink-3">
                <tr>
                  <th className="px-5 py-2.5 font-normal">Agent</th>
                  <th className="px-5 py-2.5 text-right font-normal">Runs</th>
                  <th className="px-5 py-2.5 font-normal">Completion</th>
                  <th className="hidden px-5 py-2.5 text-right font-normal sm:table-cell">Model calls per step</th>
                  <th className="px-5 py-2.5 text-right font-normal">Cost</th>
                </tr>
              </thead>
              <tbody>
                {agents.data.map((a) => (
                  <tr key={a.agent_id} className="border-t border-line/70 transition-colors hover:bg-sunk/50">
                    <td className="px-5 py-3">
                      <span className="font-medium">{a.name}</span>
                      {a.name.toLowerCase() !== a.role && <span className="ml-2 text-ink-3 capitalize">{a.role}</span>}
                    </td>
                    <td className="px-5 py-3 text-right">{num(a.runs)}</td>
                    <td className="px-5 py-3">
                      <span className="flex items-center gap-3">
                        <span className="h-1.5 w-24 overflow-hidden rounded-full bg-sunk" aria-hidden>
                          <span className="block h-full rounded-full bg-clear" style={{ width: `${Math.round((a.completion_rate ?? 0) * 100)}%` }} />
                        </span>
                        <span className="w-10 text-right">{a.completion_rate === null ? "—" : `${Math.round(a.completion_rate * 100)}%`}</span>
                      </span>
                    </td>
                    <td className="hidden px-5 py-3 text-right sm:table-cell">{a.avg_llm_calls?.toFixed(1) ?? "—"}</td>
                    <td className="px-5 py-3 text-right">{cost(a.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No agent activity in this range" />
        )}
      </Section>
    </>
  );
}
