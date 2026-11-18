import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, cx, Empty, ErrorNote, PageHeader, Section, Skeleton, Tag } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ago } from "@/lib/format";

const AUTONOMY_SHORT: Record<string, string> = {
  suggest: "Suggests only",
  act_with_approval: "Asks before acting",
  autonomous: "Acts on its own",
};

const AUTONOMY = {
  suggest: "Suggest only — every action needs a person's approval.",
  act_with_approval: "Act with approval — reads freely, asks before changing anything.",
  autonomous: "Autonomous — acts on its own; only high-risk or over-policy actions need approval.",
} as const;

function matches(pattern: string, name: string) {
  return pattern === name || (pattern.endsWith(".*") && name.startsWith(pattern.slice(0, -1)));
}

function Editor({ agent, tools }: { agent: S["AgentOut"]; tools: S["ToolOut"][] }) {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [draft, setDraft] = useState(agent);
  const editable = can("admin");
  const save = useMutation({
    mutationFn: () =>
      api.patch<S["AgentOut"]>(`/api/agents/${agent.id}`, {
        autonomy: draft.autonomy,
        allowed_tools: draft.allowed_tools,
        system_prompt: draft.system_prompt,
        max_tokens_per_run: draft.max_tokens_per_run,
        max_cost_usd_per_run: draft.max_cost_usd_per_run,
        enabled: draft.enabled,
      }),
    onSuccess: () => {
      toast(`Saved ${agent.name}`);
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const has = (t: string) => draft.allowed_tools.some((p) => matches(p, t));
  const toggle = (t: string) =>
    setDraft((d) => ({
      ...d,
      allowed_tools: has(t) ? d.allowed_tools.flatMap((p) => (p === t ? [] : matches(p, t) ? tools.filter((x) => matches(p, x.name) && x.name !== t).map((x) => x.name) : [p])) : [...d.allowed_tools, t],
    }));
  const groups = Object.entries(
    tools.reduce<Record<string, S["ToolOut"][]>>((acc, t) => ((acc[t.connector ?? "other"] ??= []).push(t), acc), {}),
  );
  return (
    <Section
      title={agent.name}
      aside={
        editable && (
          <Button variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
            Save changes
          </Button>
        )
      }
    >
      <fieldset disabled={!editable} className="space-y-5">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />
          Enabled
        </label>
        <div>
          <p className="mb-1.5 text-sm font-medium">Autonomy</p>
          <div className="grid gap-1.5">
            {Object.entries(AUTONOMY).map(([k, v]) => (
              <label key={k} className="flex items-start gap-2 text-sm">
                <input type="radio" name="autonomy" checked={draft.autonomy === k} onChange={() => setDraft({ ...draft, autonomy: k as S["Autonomy"] })} className="mt-1" />
                <span>{v}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="font-medium">Token budget per run</span>
            <input type="number" className="mt-1 w-full rounded-md border border-line bg-paper px-2 py-1.5" value={draft.max_tokens_per_run} onChange={(e) => setDraft({ ...draft, max_tokens_per_run: Number(e.target.value) })} />
          </label>
          <label className="text-sm">
            <span className="font-medium">Cost budget per run (USD)</span>
            <input type="number" step="0.05" className="mt-1 w-full rounded-md border border-line bg-paper px-2 py-1.5" value={String(draft.max_cost_usd_per_run)} onChange={(e) => setDraft({ ...draft, max_cost_usd_per_run: e.target.value })} />
          </label>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Tools this agent may use</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {groups.map(([connector, list]) => (
              <div key={connector}>
                <p className="mb-1 text-sm text-ink-3 capitalize">{connector}</p>
                {list.map((t) => (
                  <label key={t.name} className="flex items-center gap-2 py-0.5 text-sm" title={t.description}>
                    <input type="checkbox" checked={has(t.name)} onChange={() => toggle(t.name)} />
                    <code className="text-ink-2">{t.name}</code>
                    {t.risk === "high" && <Tag tone="fail">money</Tag>}
                    {t.risk === "medium" && <Tag>writes</Tag>}
                  </label>
                ))}
              </div>
            ))}
          </div>
        </div>
        <label className="block text-sm">
          <span className="font-medium">Extra instructions</span>
          <textarea rows={4} className="mt-1 w-full rounded-md border border-line bg-paper px-3 py-2" value={draft.system_prompt} onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })} />
        </label>
        <p className="text-xs text-ink-3">Model: {agent.model}</p>
      </fieldset>
    </Section>
  );
}

function Memories() {
  const { can, tenant } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["memories", tenant?.tenant_id], queryFn: () => api.get<S["MemoryOut"][]>("/api/memories", { limit: 100 }) });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/memories/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });
  return (
    <Section title="What agents remember" aside={<span className="text-sm text-ink-3">{q.data?.length ?? 0} facts</span>}>
      {q.data?.length ? (
        <ul className="divide-y divide-line text-sm">
          {q.data.map((m) => (
            <li key={m.id} className="flex items-start justify-between gap-3 py-2">
              <div>
                <p>{m.content}</p>
                <p className="text-xs text-ink-3">
                  About {m.subject_key.replace(/^contact:/, "")}, saved {ago(m.created_at)}
                </p>
              </div>
              {can("admin") && (
                <Button variant="ghost" aria-label="Forget this" onClick={() => del.mutate(m.id)}>
                  <Trash2 size={15} />
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty title="No memories yet">Agents save durable facts — preferences, budgets — as they work.</Empty>
      )}
    </Section>
  );
}

export default function Agents() {
  const { tenant } = useAuth();
  const agents = useQuery({ queryKey: ["agents", tenant?.tenant_id], queryFn: () => api.get<S["AgentOut"][]>("/api/agents") });
  const tools = useQuery({ queryKey: ["tools"], queryFn: () => api.get<S["ToolOut"][]>("/api/tools") });
  const [selected, setSelected] = useState<string | null>(null);
  const current = agents.data?.find((a) => a.id === selected) ?? agents.data?.[0];
  return (
    <>
      <PageHeader title="Agents" sub="Your specialists: what they may touch, how much they can do alone, and what they've learned." />
      <ErrorNote error={agents.error} />
      {agents.isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
          <nav aria-label="Agents" className="flex gap-2 overflow-x-auto lg:flex-col">
            {agents.data?.map((a) => (
              <button
                key={a.id}
                onClick={() => setSelected(a.id)}
                className={cx("shrink-0 rounded-md border px-3 py-2 text-left", current?.id === a.id ? "border-ink bg-panel" : "border-line hover:border-ink-3")}
              >
                <span className="block font-medium">{a.name}</span>
                <span className="block text-sm text-ink-3">{AUTONOMY_SHORT[a.autonomy]}</span>
                {!a.enabled && <span className="text-sm text-fail">Turned off</span>}
              </button>
            ))}
          </nav>
          <div className="space-y-4">
            {current && tools.data && <Editor key={`${current.id}:${current.updated_at}`} agent={current} tools={tools.data} />}
            <Memories />
          </div>
        </div>
      )}
    </>
  );
}
