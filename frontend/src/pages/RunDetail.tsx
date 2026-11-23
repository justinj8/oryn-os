import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ExternalLink, Hand, RotateCcw, ShieldCheck, ShieldX } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { RunRoute } from "@/components/runs/RouteBoard";
import { SpanDetail } from "@/components/trace/SpanDetail";
import { TraceWaterfall, type SpanLike } from "@/components/trace/TraceWaterfall";
import { Button, cx, Drawer, Empty, ErrorNote, Figure, Json, PageHeader, Section, Skeleton, StatusPill, Tag } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { useNow } from "@/hooks/useNow";
import { ago, cost, duration, humanize, num, usd } from "@/lib/format";

const TEMPORAL_UI = import.meta.env.VITE_TEMPORAL_UI ?? "http://localhost:8233";

export default function RunDetail() {
  const { runId = "" } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<SpanLike | null>(null);
  const now = useNow(1000);
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.get<S["RunDetail"]>(`/api/runs/${runId}`),
    refetchInterval: (q) => (q.state.data && ["running", "waiting_approval"].includes(q.state.data.status) ? 3000 : false),
  });
  const spans = useQuery({
    queryKey: ["run", runId, "spans"],
    queryFn: () => api.get<S["SpanOut"][]>(`/api/runs/${runId}/spans`),
    refetchInterval: () => (run.data && ["running", "waiting_approval"].includes(run.data.status) ? 3000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => api.post(`/api/runs/${runId}/cancel`),
    onSuccess: () => {
      toast("Cancellation requested");
      qc.invalidateQueries({ queryKey: ["run", runId] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const navigate = useNavigate();
  // One key per intent: a double click starts one run; after it succeeds the next click is a new intent.
  const [rerunKey, setRerunKey] = useState(() => crypto.randomUUID());
  const rerun = useMutation({
    mutationFn: () => api.post<S["IngestOut"]>(`/api/runs/${runId}/rerun`, {}, { "Idempotency-Key": rerunKey }),
    onSuccess: (res) => {
      setRerunKey(crypto.randomUUID());
      qc.invalidateQueries({ queryKey: ["runs"] });
      toast("Started a new run from the same event");
      if (res.run_ids[0]) navigate(`/runs/${res.run_ids[0]}`);
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  if (run.isLoading) return <Skeleton className="h-72" />;
  if (run.error || !run.data) return <ErrorNote error={run.error ?? new Error("Run not found")} />;
  const r = run.data;
  const live = r.status === "running" || r.status === "waiting_approval";
  const elapsed = r.duration_s ?? (now - new Date(r.started_at).getTime()) / 1000;
  const outcomeValue = r.outcomes.reduce((s, o) => s + Number(o.value_usd), 0);
  // The route for the header comes from the agent spans, the same way the run list builds it.
  const route: string[] = [];
  for (const s of spans.data ?? []) {
    if (s.kind !== "agent") continue;
    const agent = s.name.split(" · ")[0];
    if (route[route.length - 1] !== agent) route.push(agent);
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-5 flex items-center gap-1 text-sm text-ink-3">
        <Link to="/runs" className="hover:text-ink">
          Runs
        </Link>
        <ChevronRight size={14} aria-hidden />
        <span className="truncate text-ink-2">{r.title || "Run"}</span>
      </nav>

      <PageHeader
        title={r.title || "Run"}
        sub={
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <StatusPill status={r.status} />
            <span title={new Date(r.started_at).toLocaleString()}>Started {ago(r.started_at)}</span>
            <span className="capitalize">{r.kind}</span>
          </span>
        }
        actions={
          <>
            <a
              className="inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] text-accent transition-colors hover:bg-accent/8"
              href={`${TEMPORAL_UI}/namespaces/default/workflows/${encodeURIComponent(r.temporal_workflow_id)}`}
              target="_blank"
              rel="noreferrer"
            >
              Open in Temporal <ExternalLink size={14} aria-hidden />
            </a>
            {!live && r.rerunnable && can("operator") && (
              <Button onClick={() => rerun.mutate()} disabled={rerun.isPending} title="Start this workflow again from the event that started it">
                <RotateCcw size={15} aria-hidden /> {rerun.isPending ? "Starting…" : "Run again"}
              </Button>
            )}
            {live && can("operator") && (
              <Button variant="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
                Cancel run
              </Button>
            )}
          </>
        }
      />

      {route.length > 0 && (
        <div className="card mb-6 px-5 py-4">
          <RunRoute run={{ ...r, route }} />
        </div>
      )}

      {r.status === "waiting_approval" && (
        <Link
          to="/approvals"
          className="card mb-6 flex items-center gap-3.5 px-5 py-4 text-[15px] transition-transform active:scale-[0.995]"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-hold text-white">
            <Hand size={15} aria-hidden />
          </span>
          <span className="flex-1">This run is paused until someone approves or rejects the pending action.</span>
          <span className="text-[14px] font-medium text-accent">Go to approvals</span>
        </Link>
      )}

      <dl className="card mb-6 grid grid-cols-2 gap-y-6 p-5 sm:grid-cols-4 sm:divide-x sm:divide-line/70">
        <div className="pr-6">
          <Figure label="Duration" value={duration(elapsed)} />
        </div>
        <div className="pr-6 sm:pl-6">
          <Figure label="Model cost" value={cost(r.total_cost_usd)} note={r.simulated_cost ? <Tag>simulated</Tag> : null} />
        </div>
        <div className="pr-6 sm:pl-6">
          <Figure label="Tokens in / out" value={`${num(r.total_input_tokens)} / ${num(r.total_output_tokens)}`} />
        </div>
        <div className="sm:pl-6">
          <dt className="text-[13px] text-ink-3">Outcome</dt>
          <dd className="mt-1.5">
            {r.outcomes.length ? (
              <>
                <span className="block font-figure text-[30px]">{outcomeValue ? usd(outcomeValue) : "Done"}</span>
                <span className="text-[13px] text-ink-2">
                  {r.outcomes.map((o) => `${humanize(o.type)}${Number(o.value_usd) ? ` (${usd(o.value_usd)})` : ""}`).join(", ")}
                </span>
              </>
            ) : (
              <span className="font-figure text-[30px] text-ink-3">—</span>
            )}
          </dd>
        </div>
      </dl>

      {r.outcome_summary && <p className="mb-8 max-w-3xl text-[17px] leading-relaxed text-ink-2">{r.outcome_summary}</p>}
      {r.error && (
        <div className="mb-8">
          <ErrorNote error={new Error(r.error)} />
        </div>
      )}

      <Section
        title="Trace"
        aside={
          <span>
            {spans.data?.length ?? 0} steps{live && <span className="ml-2 text-accent">updating</span>}
          </span>
        }
      >
        {spans.data?.length ? (
          <TraceWaterfall spans={spans.data} onSelect={setSelected} selectedId={selected?.id} />
        ) : (
          <Empty title="No steps recorded yet">Steps appear here the moment an agent starts working.</Empty>
        )}
      </Section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Section title="Approvals">
          {r.approvals.length ? (
            <ol className="space-y-4">
              {r.approvals.map((a) => {
                const ok = a.status === "approved";
                const pending = a.status === "pending";
                return (
                  <li key={a.id} className="flex gap-3">
                    <span
                      className={cx(
                        "mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                        pending ? "bg-hold/12 text-hold" : ok ? "bg-clear/12 text-clear" : "bg-sunk text-ink-3",
                      )}
                      aria-hidden
                    >
                      {pending ? <Hand size={14} /> : ok ? <ShieldCheck size={14} /> : <ShieldX size={14} />}
                    </span>
                    <span className="text-sm">
                      <span className="block font-medium text-ink">{a.description}</span>
                      <span className="text-ink-3">
                        {humanize(a.status)}
                        {a.comment ? `: “${a.comment}”` : ""}. Needed an {a.min_role} or above.
                      </span>
                    </span>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="text-sm text-ink-3">No human approval was needed.</p>
          )}
        </Section>
        <Section title="Shared facts" aside="What the agents told each other">
          {Object.keys(r.blackboard).length ? <Json value={r.blackboard} /> : <p className="text-sm text-ink-3">Nothing shared yet.</p>}
        </Section>
      </div>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ""}>
        {selected && <SpanDetail span={selected} />}
      </Drawer>
    </>
  );
}
