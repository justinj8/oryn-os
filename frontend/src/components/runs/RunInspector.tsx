import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ExternalLink, Hand, RotateCcw, ShieldCheck, ShieldX, Square } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { RunRoute } from "@/components/runs/RouteBoard";
import { SpanDetail } from "@/components/trace/SpanDetail";
import { TraceWaterfall, type SpanLike } from "@/components/trace/TraceWaterfall";
import { Button, cx, Drawer, Empty, ErrorNote, Json, Segmented, Skeleton, StatusPill, Tag, Toolbar } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { useNow } from "@/hooks/useNow";
import { ago, cost, duration, humanize, num, usd } from "@/lib/format";

export const TEMPORAL_UI = import.meta.env.VITE_TEMPORAL_UI ?? "http://localhost:8233";
const LIVE = ["running", "waiting_approval"];

export function useRerun(runId: string) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  // One key per intent: a double click starts one run; after it succeeds the next click is a new intent.
  const [key, setKey] = useState(() => crypto.randomUUID());
  return useMutation({
    mutationFn: () => api.post<S["IngestOut"]>(`/api/runs/${runId}/rerun`, {}, { "Idempotency-Key": key }),
    onSuccess: (res) => {
      setKey(crypto.randomUUID());
      qc.invalidateQueries({ queryKey: ["runs"] });
      toast("Started a new run from the same event");
      if (res.run_ids[0]) navigate(`/runs/${res.run_ids[0]}`);
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
}

/** Everything about one run, shown beside the list: route, numbers, trace, approvals and shared facts. */
export function RunInspector({ runId, onBack }: { runId: string; onBack?: () => void }) {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"trace" | "approvals" | "facts">("trace");
  const [selected, setSelected] = useState<SpanLike | null>(null);
  const now = useNow(1000);
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.get<S["RunDetail"]>(`/api/runs/${runId}`),
    refetchInterval: (q) => (q.state.data && LIVE.includes(q.state.data.status) ? 3000 : false),
  });
  const spans = useQuery({
    queryKey: ["run", runId, "spans"],
    queryFn: () => api.get<S["SpanOut"][]>(`/api/runs/${runId}/spans`),
    refetchInterval: () => (run.data && LIVE.includes(run.data.status) ? 3000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => api.post(`/api/runs/${runId}/cancel`),
    onSuccess: () => {
      toast("Cancellation requested");
      qc.invalidateQueries({ queryKey: ["run", runId] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const rerun = useRerun(runId);

  const r = run.data;
  const live = !!r && LIVE.includes(r.status);
  const back = onBack && (
    <button onClick={onBack} className="-ml-1 flex items-center text-[13px] text-accent lg:hidden" aria-label="Back to runs">
      <ChevronLeft size={18} /> Runs
    </button>
  );

  if (run.isLoading)
    return (
      <div className="flex min-w-0 flex-1 flex-col">
        <Toolbar leading={back} />
        <div className="space-y-4 p-6">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-24" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  if (run.error || !r)
    return (
      <div className="flex min-w-0 flex-1 flex-col">
        <Toolbar leading={back} />
        <div className="p-6">
          <ErrorNote error={run.error ?? new Error("Run not found")} />
        </div>
      </div>
    );

  const elapsed = r.duration_s ?? (now - new Date(r.started_at).getTime()) / 1000;
  const outcomeValue = r.outcomes.reduce((s, o) => s + Number(o.value_usd), 0);
  const route: string[] = [];
  for (const s of spans.data ?? []) {
    if (s.kind !== "agent") continue;
    const agent = s.name.split(" · ")[0];
    if (route[route.length - 1] !== agent) route.push(agent);
  }

  return (
    <section aria-label="Run details" className="flex min-w-0 flex-1 flex-col">
      <Toolbar leading={back}>
        {!live && r.rerunnable && can("operator") && (
          <Button size="sm" onClick={() => rerun.mutate()} disabled={rerun.isPending} title="Start this workflow again from the event that started it">
            <RotateCcw size={13} aria-hidden /> {rerun.isPending ? "Starting…" : "Run again"}
          </Button>
        )}
        {live && can("operator") && (
          <Button size="sm" variant="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
            <Square size={11} fill="currentColor" aria-hidden /> Cancel run
          </Button>
        )}
        <a
          className="flex h-7 w-7 items-center justify-center rounded-md text-ink-2 hover:bg-fill hover:text-ink"
          href={`${TEMPORAL_UI}/namespaces/default/workflows/${encodeURIComponent(r.temporal_workflow_id)}`}
          target="_blank"
          rel="noreferrer"
          title="Open in Temporal"
          aria-label="Open in Temporal"
        >
          <ExternalLink size={14} />
        </a>
        <span className="mx-1 h-4 w-px bg-line" aria-hidden />
      </Toolbar>

      <div key={runId} className="min-h-0 flex-1 animate-[fade_180ms_ease-out] overflow-y-auto">
        <div className="px-6 pt-6 pb-10 xl:px-8">
          <h2 className="text-[22px] leading-tight font-semibold tracking-[-0.02em] text-balance">{r.title || "Untitled run"}</h2>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-3">
            <StatusPill status={r.status} />
            <span title={new Date(r.started_at).toLocaleString()}>Started {ago(r.started_at)}</span>
            <span className="capitalize">{r.kind}</span>
          </div>

          {route.length > 0 && (
            <div className="mt-5 rounded-xl bg-group px-4 py-3 shadow-[inset_0_0_0_0.5px_var(--line)]">
              <RunRoute run={{ ...r, route }} />
            </div>
          )}

          {r.status === "waiting_approval" && (
            <Link to="/approvals" className="mt-3 flex items-center gap-3 rounded-xl bg-hold/10 px-4 py-3 text-[13px] transition-colors hover:bg-hold/15">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-hold text-white">
                <Hand size={12} aria-hidden />
              </span>
              <span className="flex-1">Paused until someone approves or rejects the pending action.</span>
              <span className="font-medium text-accent">Review</span>
            </Link>
          )}

          <dl className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-line/70 shadow-[inset_0_0_0_0.5px_var(--line)] sm:grid-cols-4">
            {[
              ["Duration", duration(elapsed), null],
              ["Model cost", cost(r.total_cost_usd), r.simulated_cost ? <Tag key="s">simulated</Tag> : null],
              ["Tokens in / out", `${num(r.total_input_tokens)} / ${num(r.total_output_tokens)}`, null],
              ["Outcome", outcomeValue ? usd(outcomeValue) : r.outcomes.length ? "Done" : "—", null],
            ].map(([label, value, note]) => (
              <div key={String(label)} className="bg-group px-4 py-3">
                <dt className="text-[11.5px] text-ink-3">{label}</dt>
                <dd className="mt-1 flex items-baseline gap-1.5">
                  <span className="font-figure text-[19px]">{value}</span>
                  {note}
                </dd>
              </div>
            ))}
          </dl>
          {r.outcomes.length > 0 && (
            <p className="mt-2 text-[12.5px] text-clear">{r.outcomes.map((o) => `${humanize(o.type)}${Number(o.value_usd) ? ` (${usd(o.value_usd)})` : ""}`).join(", ")}</p>
          )}
          {r.outcome_summary && <p className="mt-4 max-w-2xl text-[14px] leading-relaxed text-ink-2">{r.outcome_summary}</p>}
          {r.error && (
            <div className="mt-4">
              <ErrorNote error={new Error(r.error)} />
            </div>
          )}

          <div className="mt-7 flex items-center justify-between gap-3">
            <Segmented
              label="Show"
              value={tab}
              onChange={setTab}
              options={[
                { value: "trace", label: `Trace${spans.data ? ` ${spans.data.length}` : ""}` },
                { value: "approvals", label: `Approvals${r.approvals.length ? ` ${r.approvals.length}` : ""}` },
                { value: "facts", label: "Shared facts" },
              ]}
            />
            {live && tab === "trace" && <span className="text-[12px] text-accent">Updating live</span>}
          </div>

          <div className="mt-4">
            {tab === "trace" &&
              (spans.data?.length ? (
                <TraceWaterfall spans={spans.data} onSelect={setSelected} selectedId={selected?.id} />
              ) : (
                <Empty title="No steps recorded yet">Steps appear the moment an agent starts working.</Empty>
              ))}
            {tab === "approvals" &&
              (r.approvals.length ? (
                <ol className="space-y-3">
                  {r.approvals.map((a) => {
                    const ok = a.status === "approved";
                    const pending = a.status === "pending";
                    return (
                      <li key={a.id} className="flex gap-3 rounded-xl bg-group p-3.5 shadow-[inset_0_0_0_0.5px_var(--line)]">
                        <span
                          className={cx(
                            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white",
                            pending ? "bg-hold" : ok ? "bg-clear" : "bg-idle",
                          )}
                          aria-hidden
                        >
                          {pending ? <Hand size={13} /> : ok ? <ShieldCheck size={13} /> : <ShieldX size={13} />}
                        </span>
                        <span className="text-[13px]">
                          <span className="block font-medium text-ink">{a.description}</span>
                          <span className="text-ink-3">
                            {humanize(a.status)}
                            {a.comment ? `: “${a.comment}”` : ""}. Needs an {a.min_role} or above.
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ol>
              ) : (
                <p className="text-[13px] text-ink-3">No human approval was needed.</p>
              ))}
            {tab === "facts" &&
              (Object.keys(r.blackboard).length ? <Json value={r.blackboard} /> : <p className="text-[13px] text-ink-3">The agents haven't shared anything yet.</p>)}
          </div>
        </div>
      </div>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ""}>
        {selected && <SpanDetail span={selected} />}
      </Drawer>
    </section>
  );
}
