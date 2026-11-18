import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { SpanDetail } from "@/components/trace/SpanDetail";
import { TraceWaterfall, type SpanLike } from "@/components/trace/TraceWaterfall";
import { Button, Drawer, Empty, ErrorNote, Json, PageHeader, Section, Skeleton, StatusPill, Tag } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { useNow } from "@/hooks/useNow";
import { cost, duration, humanize, num, usd } from "@/lib/format";

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

  if (run.isLoading) return <Skeleton className="h-64" />;
  if (run.error || !run.data) return <ErrorNote error={run.error ?? new Error("Run not found")} />;
  const r = run.data;
  const live = r.status === "running" || r.status === "waiting_approval";
  const elapsed = r.duration_s ?? (now - new Date(r.started_at).getTime()) / 1000;

  return (
    <>
      <p className="mb-2 text-sm">
        <Link to="/runs" className="text-ink-3 hover:text-ink">
          Runs
        </Link>
      </p>
      <PageHeader
        title={r.title || "Run"}
        sub={<StatusPill status={r.status} />}
        actions={
          <>
            <a
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-ink-2 hover:bg-line/50"
              href={`${TEMPORAL_UI}/namespaces/default/workflows/${encodeURIComponent(r.temporal_workflow_id)}`}
              target="_blank"
              rel="noreferrer"
            >
              Open in Temporal <ExternalLink size={14} aria-hidden />
            </a>
            {live && can("operator") && (
              <Button variant="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
                Cancel run
              </Button>
            )}
          </>
        }
      />

      <dl className="mb-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-ink-3">Duration</dt>
          <dd className="font-medium">{duration(elapsed)}</dd>
        </div>
        <div>
          <dt className="text-ink-3">Model cost</dt>
          <dd className="font-medium">
            {cost(r.total_cost_usd)} {r.simulated_cost && <Tag>simulated</Tag>}
          </dd>
        </div>
        <div>
          <dt className="text-ink-3">Tokens in / out</dt>
          <dd className="font-medium">
            {num(r.total_input_tokens)} / {num(r.total_output_tokens)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-3">Outcome</dt>
          <dd className="font-medium">
            {r.outcomes.length ? r.outcomes.map((o) => `${humanize(o.type)}${Number(o.value_usd) ? ` (${usd(o.value_usd)})` : ""}`).join(", ") : "—"}
          </dd>
        </div>
      </dl>
      {r.outcome_summary && <p className="mb-6 max-w-3xl text-ink-2">{r.outcome_summary}</p>}
      {r.error && <ErrorNote error={new Error(r.error)} />}

      <Section title="Trace" aside={<span className="text-sm text-ink-3">{spans.data?.length ?? 0} steps</span>}>
        {spans.data?.length ? (
          <TraceWaterfall spans={spans.data} onSelect={setSelected} selectedId={selected?.id} />
        ) : (
          <Empty title="No steps recorded yet" />
        )}
      </Section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Section title="Approvals">
          {r.approvals.length ? (
            <ul className="space-y-3 text-sm">
              {r.approvals.map((a) => (
                <li key={a.id} className="border-l-4 border-hold pl-3">
                  <p className="font-medium">{a.description}</p>
                  <p className="text-ink-3">
                    {humanize(a.status)}
                    {a.comment ? `: ${a.comment}` : ""} · needs {a.min_role}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-3">No human approval was needed.</p>
          )}
        </Section>
        <Section title="Shared facts (blackboard)">
          {Object.keys(r.blackboard).length ? <Json value={r.blackboard} /> : <p className="text-sm text-ink-3">Nothing shared yet.</p>}
        </Section>
      </div>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ""}>
        {selected && <SpanDetail span={selected} />}
      </Drawer>
    </>
  );
}
