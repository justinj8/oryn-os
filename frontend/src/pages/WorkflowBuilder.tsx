import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, cx, ErrorNote, Json, PageHeader, Section, Tag } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { WorkflowGraph, type Definition } from "@/components/workflow/WorkflowGraph";

export default function WorkflowBuilder() {
  const { workflowId } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [tab, setTab] = useState<"graph" | "json">("graph");
  const existing = useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: () => api.get<S["WorkflowDetail"]>(`/api/workflows/${workflowId}`),
    enabled: !!workflowId,
  });
  const examples = useQuery({ queryKey: ["workflow-examples"], queryFn: () => api.get<string[]>("/api/workflows/examples") });
  const draft = useMutation({ mutationFn: (t: string) => api.post<S["DraftResult"]>("/api/workflows/draft", { text: t }) });
  const save = useMutation({
    mutationFn: (d: Definition) =>
      workflowId
        ? api.post<S["WorkflowDetail"]>(`/api/workflows/${workflowId}/versions`, { definition: d, source_text: text })
        : api.post<S["WorkflowDetail"]>("/api/workflows", { definition: d, source_text: text }),
    onSuccess: (w) => {
      toast(workflowId ? `Saved version ${w.current_version}` : `Created “${w.name}”`);
      qc.invalidateQueries({ queryKey: ["workflows"] });
      qc.invalidateQueries({ queryKey: ["workflow", w.id] });
      draft.reset();
      nav(`/workflows/${w.id}`);
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const result = draft.data;
  const shown = (result?.definition ?? existing.data?.definition) as Definition | undefined;
  const canSave = !!result?.definition && result.errors.length === 0 && can("admin");

  return (
    <>
      <p className="mb-2 text-sm">
        <Link to="/workflows" className="text-ink-3 hover:text-ink">
          Workflows
        </Link>
      </p>
      <PageHeader
        title={existing.data?.name ?? "New workflow"}
        sub={existing.data ? `Version ${existing.data.current_version}, starts when ${existing.data.trigger_event} arrives.` : "Describe what should happen in a sentence or two."}
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Section title={workflowId ? "Describe a new version" : "Describe it"}>
          <label htmlFor="nl" className="sr-only">
            Workflow description
          </label>
          <textarea
            id="nl"
            rows={7}
            value={text}
            placeholder={existing.data?.source_text ?? "When a new lead arrives, have the sales agent qualify the lead…"}
            onChange={(e) => setText(e.target.value)}
            className="w-full field"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => draft.mutate(text)} disabled={!text.trim() || draft.isPending || !can("admin")}>
              {draft.isPending ? "Building…" : "Build workflow"}
            </Button>
            {canSave && (
              <Button onClick={() => save.mutate(result!.definition as unknown as Definition)} disabled={save.isPending}>
                {workflowId ? "Save as new version" : "Save workflow"}
              </Button>
            )}
          </div>
          {!can("admin") && <p className="mt-2 text-sm text-ink-3">Only admins can change workflows.</p>}
          <ErrorNote error={draft.error} />
          {result && (
            <div className="mt-4 space-y-2 text-sm">
              {result.errors.map((e) => (
                <p key={e} className="text-fail">
                  {e}
                </p>
              ))}
              {result.warnings.map((w) => (
                <p key={w} className="text-hold">
                  {w}
                </p>
              ))}
              {result.clauses.length > 0 && (
                <ul className="space-y-1">
                  {result.clauses.map((c, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <Tag tone={c.rule ? "clear" : "fail"}>{c.rule ?? "not understood"}</Tag>
                      <span className="text-ink-2">{c.text}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="mt-5 border-t border-line pt-3">
            <p className="mb-2 text-sm text-ink-3">Try one of these</p>
            <div className="flex flex-col gap-1.5">
              {examples.data?.map((ex) => (
                <button key={ex} onClick={() => setText(ex)} className="rounded-md border border-line px-3 py-2 text-left text-sm text-ink-2 hover:border-ink-3">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </Section>
        <Section
          title={result ? "Draft" : "Current version"}
          aside={
            <div className="inline-flex rounded-md border border-line p-0.5 text-sm">
              {(["graph", "json"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={cx("rounded px-2 py-0.5", tab === t ? "bg-ink text-paper" : "text-ink-2")}>
                  {t === "graph" ? "Graph" : "JSON"}
                </button>
              ))}
            </div>
          }
        >
          {shown ? tab === "graph" ? <WorkflowGraph definition={shown} /> : <Json value={shown} /> : <p className="text-sm text-ink-3">Build a workflow to see it here.</p>}
          {existing.data && existing.data.versions.length > 1 && (
            <p className="mt-3 text-sm text-ink-3">
              Earlier versions: {existing.data.versions.slice(1).map((v) => `v${v.version}`).join(", ")}. Runs already in progress keep the version they started with.
            </p>
          )}
        </Section>
      </div>
    </>
  );
}
