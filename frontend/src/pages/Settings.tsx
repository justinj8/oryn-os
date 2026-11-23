import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, ErrorNote, PageHeader, Section } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ago } from "@/lib/format";

const ROLES = ["viewer", "operator", "admin", "owner"] as const;

function Members() {
  const { can, tenant, user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["members", tenant?.tenant_id], queryFn: () => api.get<S["MemberOut"][]>("/api/members") });
  const [form, setForm] = useState({ email: "", name: "", role: "operator", password: "" });
  const invite = useMutation({
    mutationFn: () => api.post("/api/members", { ...form, password: form.password || null }),
    onSuccess: () => {
      toast(`Added ${form.email}`);
      setForm({ email: "", name: "", role: "operator", password: "" });
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const change = useMutation({
    mutationFn: (v: { id: string; role: string }) => api.patch(`/api/members/${v.id}`, { role: v.role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members"] }),
    onError: (e) => toast((e as Error).message, "error"),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    invite.mutate();
  };
  return (
    <Section title="People">
      <table className="w-full text-sm">
        <tbody>
          {q.data?.map((m) => (
            <tr key={m.user_id} className="border-b border-line last:border-0">
              <td className="py-2">
                <span className="font-medium">{m.name}</span>
                <span className="block text-ink-3">{m.email}</span>
              </td>
              <td className="py-2 text-right">
                {can("owner") && m.user_id !== user?.id ? (
                  <select value={m.role} onChange={(e) => change.mutate({ id: m.user_id, role: e.target.value })} aria-label={`Role for ${m.name}`} className="field capitalize">
                    {ROLES.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                ) : (
                  <span className="capitalize">{m.role}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {can("owner") && (
        <form onSubmit={submit} className="mt-4 grid gap-2 border-t border-line pt-4 text-sm sm:grid-cols-2">
          <input required placeholder="Email" aria-label="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="field" />
          <input required placeholder="Name" aria-label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="field" />
          <select aria-label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="field capitalize">
            {ROLES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <input placeholder="Temporary password (optional)" aria-label="Temporary password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="field" />
          <Button type="submit" variant="primary" disabled={invite.isPending} className="sm:col-span-2">
            Add person
          </Button>
        </form>
      )}
    </Section>
  );
}

function ApiKeys() {
  const { tenant } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["api-keys", tenant?.tenant_id], queryFn: () => api.get<S["ApiKeyOut"][]>("/api/api-keys") });
  const create = useMutation({
    mutationFn: () => api.post<S["ApiKeyCreated"]>("/api/api-keys", { name }),
    onSuccess: (k) => {
      setCreated(k.key);
      setName("");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.del(`/api/api-keys/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }) });
  return (
    <Section title="API keys">
      <p className="mb-3 text-sm text-ink-3">For your own systems, webhooks, the public agent API (/v1) and the MCP server.</p>
      {created && (
        <div className="mb-3 rounded-md border border-hold/40 bg-hold/10 p-3 text-sm">
          <p className="font-medium">Copy this key now — it won't be shown again.</p>
          <code className="mt-1 block break-all">{created}</code>
        </div>
      )}
      <ul className="text-sm">
        {q.data?.map((k) => (
          <li key={k.id} className="flex items-center justify-between border-b border-line py-2 last:border-0">
            <span>
              <span className="font-medium">{k.name}</span> <code className="text-ink-3">oryn_{k.prefix}_…</code>
              <span className="block text-xs text-ink-3">{k.revoked_at ? "Revoked" : `Last used ${ago(k.last_used_at)}`}</span>
            </span>
            {!k.revoked_at && (
              <Button variant="danger" onClick={() => revoke.mutate(k.id)}>
                Revoke
              </Button>
            )}
          </li>
        ))}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
        className="mt-3 flex gap-2"
      >
        <input required placeholder="Key name, e.g. CRM webhook" aria-label="Key name" value={name} onChange={(e) => setName(e.target.value)} className="min-w-0 flex-1 field text-sm" />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Create key
        </Button>
      </form>
    </Section>
  );
}

function Audit() {
  const { tenant } = useAuth();
  const q = useQuery({ queryKey: ["audit", tenant?.tenant_id], queryFn: () => api.get<S["AuditOut"][]>("/api/audit", { limit: 50 }) });
  return (
    <Section title="Audit log">
      <ErrorNote error={q.error} />
      <ul className="text-sm">
        {q.data?.map((a) => (
          <li key={a.id} className="flex justify-between gap-3 border-b border-line py-1.5 last:border-0">
            <code>{a.action}</code>
            <span className="text-ink-3">{ago(a.created_at)}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export default function Settings() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader title="Settings" sub="Who can do what, and how other systems connect." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Members />
        {can("owner") && <ApiKeys />}
        {can("admin") && <Audit />}
      </div>
    </>
  );
}
