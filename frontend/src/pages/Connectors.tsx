import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, cx, Empty, ErrorNote, PageHeader, Section, Skeleton, Tag } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ago, humanize } from "@/lib/format";

const KIND_LABEL: Record<string, string> = {
  crm: "CRM", email: "Email", sms: "SMS", voice: "Voice", calendar: "Calendar", billing: "Billing",
  database: "Internal database", docs: "Knowledge base", chat: "Website chat",
};

function ConnectorCard({ c }: { c: S["ConnectorOut"] }) {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [rate, setRate] = useState(Number(c.settings.failure_rate ?? 0));
  const [latency, setLatency] = useState(Number(c.settings.latency_ms ?? 0));
  const [outage, setOutage] = useState(Number(c.settings.fail_attempts ?? 0));
  const save = useMutation({
    mutationFn: () => api.patch(`/api/connectors/${c.id}`, { settings: { failure_rate: rate, latency_ms: latency, fail_attempts: outage } }),
    onSuccess: () => {
      toast(`${KIND_LABEL[c.kind] ?? c.kind} fault settings saved`);
      qc.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-lg font-semibold">{KIND_LABEL[c.kind] ?? c.kind}</p>
          <p className="text-sm text-ink-3">{c.name}</p>
        </div>
        <Tag tone={c.provider === "sandbox" ? "neutral" : "clear"}>{c.provider === "sandbox" ? "Sandbox" : humanize(c.provider)}</Tag>
      </div>
      {can("admin") && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-ink-2">Simulate an unreliable service</summary>
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="flex justify-between">
                Random failures <span className="text-ink-3">{Math.round(rate * 100)}%</span>
              </span>
              <input type="range" min={0} max={0.6} step={0.05} value={rate} onChange={(e) => setRate(Number(e.target.value))} className="w-full" />
            </label>
            <label className="block">
              <span className="flex justify-between">
                Added latency <span className="text-ink-3">{latency} ms</span>
              </span>
              <input type="range" min={0} max={2000} step={50} value={latency} onChange={(e) => setLatency(Number(e.target.value))} className="w-full" />
            </label>
            <label className="flex items-center justify-between gap-2">
              Outage for first attempts
              <select value={outage} onChange={(e) => setOutage(Number(e.target.value))} className="field">
                {[0, 1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n === 0 ? "None" : `${n}`}
                  </option>
                ))}
              </select>
            </label>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              Save
            </Button>
          </div>
        </details>
      )}
    </div>
  );
}

const TABS = ["contacts", "deals", "calendar", "messages", "invoices", "tickets", "documents"] as const;
const HIDDEN = new Set(["id", "contact_id", "conversation_id", "attributes", "created_at"]);

function SandboxBrowser() {
  const { tenant } = useAuth();
  const [tab, setTab] = useState<(typeof TABS)[number]>("contacts");
  const q = useQuery({
    queryKey: ["sandbox", tab, tenant?.tenant_id],
    queryFn: () => api.get<S["SandboxPage"]>(`/api/sandbox/${tab}`, { limit: 50 }),
  });
  const cols = q.data?.items[0] ? Object.keys(q.data.items[0]).filter((k) => !HIDDEN.has(k)) : [];
  const cell = (v: unknown, k: string) =>
    v === null || v === undefined ? "—" : k.endsWith("_at") ? ago(String(v)) : typeof v === "object" ? JSON.stringify(v) : String(v);
  return (
    <Section
      title="Sandbox data"
      aside={<span className="text-sm text-ink-3">The simulated systems your agents act on</span>}
      className="mt-6"
    >
      <div role="tablist" className="mb-3 flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={cx("rounded-md px-2.5 py-1 text-sm", tab === t ? "bg-ink text-paper" : "text-ink-2 hover:bg-line/50")}>
            {humanize(t)}
          </button>
        ))}
      </div>
      <ErrorNote error={q.error} />
      {q.data?.items.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-ink-3">
              <tr>
                {cols.map((c) => (
                  <th key={c} className="py-1.5 pr-4 font-normal">
                    {humanize(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((row) => (
                <tr key={String(row.id)} className="border-t border-line align-top">
                  {cols.map((c) => (
                    <td key={c} className="max-w-xs truncate py-1.5 pr-4" title={String(row[c] ?? "")}>
                      {cell(row[c], c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-ink-3">{q.data.total} total</p>
        </div>
      ) : (
        <Empty title={`No ${tab} yet`} />
      )}
    </Section>
  );
}

export default function Connectors() {
  const { tenant } = useAuth();
  const q = useQuery({ queryKey: ["connectors", tenant?.tenant_id], queryFn: () => api.get<S["ConnectorOut"][]>("/api/connectors") });
  return (
    <>
      <PageHeader
        title="Connectors"
        sub="The systems agents work in. Sandbox connectors run offline; set Twilio or SMTP keys to send real texts and email."
      />
      <ErrorNote error={q.error} />
      {q.isLoading ? (
        <Skeleton className="h-40" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {q.data?.map((c) => (
            <ConnectorCard key={c.id} c={c} />
          ))}
        </div>
      )}
      <SandboxBrowser />
    </>
  );
}
