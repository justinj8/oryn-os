import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { ChatSim } from "@/components/sim/ChatSim";
import { EmailSim } from "@/components/sim/EmailSim";
import { PhoneSim } from "@/components/sim/PhoneSim";
import { Button, PageHeader, Section } from "@/components/ui";
import { useToast } from "@/components/ui/toast";

const PRESETS: { label: string; hint: string; type: string; payload: () => Record<string, unknown> }[] = [
  {
    label: "New lead asking for a 15% discount",
    hint: "Sales qualifies, asks a manager about the discount, then hands off to scheduling.",
    type: "lead.created",
    payload: () => ({ name: "Dana Reyes", email: `dana.${Date.now()}@example.com`, phone: "+15550101", company: "Reyes Co", need: "heat pump install", budget_usd: 8200, requested_discount_pct: 15, source: "web" }),
  },
  {
    label: "New lead with a small budget",
    hint: "Not qualified yet — goes to the nurture email.",
    type: "lead.created",
    payload: () => ({ name: "Sam Patel", email: `sam.${Date.now()}@example.com`, need: "AC tune-up", budget_usd: 600, source: "web" }),
  },
  {
    label: "Support ticket: refund of $750",
    hint: "Over the admin threshold — needs an admin to approve.",
    type: "ticket.created",
    payload: () => ({ name: "Ann Lee", email: "ann.lee@example.com", subject: "Refund", body: "Please refund $750 on INV-1001" }),
  },
  {
    label: "Overdue invoices",
    hint: "The ops agent texts payment reminders.",
    type: "invoice.overdue",
    payload: () => ({}),
  },
  { label: "Weekly report", hint: "The reporting agent queries the warehouse and emails a summary.", type: "schedule.weekly", payload: () => ({}) },
];

export default function Simulators() {
  const { tenant, can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const slug = tenant?.slug ?? "";
  const traffic = useQuery({ queryKey: ["traffic", tenant?.tenant_id], queryFn: () => api.get<{ enabled: boolean; rate_per_min: number }>("/api/simulate/traffic") });
  const fire = useMutation({
    mutationFn: (p: (typeof PRESETS)[number]) => api.post<S["IngestOut"]>("/api/simulate/events", { type: p.type, payload: p.payload() }),
    onSuccess: (r) => {
      toast(r.run_ids.length ? `Started ${r.run_ids.length} run${r.run_ids.length > 1 ? "s" : ""}` : "Event received — no workflow listens for it");
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const setTraffic = useMutation({
    mutationFn: (v: { enabled: boolean; rate_per_min: number }) => api.post("/api/simulate/traffic", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["traffic"] }),
  });
  const t = traffic.data;

  return (
    <>
      <PageHeader
        title="Simulators"
        sub={
          <>
            Play the outside world. Everything here goes through the same webhooks and workflows a real customer would — watch it on the{" "}
            <Link to="/" className="text-flight hover:underline">
              Overview
            </Link>
            .
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Fire an event">
          <ul className="space-y-2">
            {PRESETS.map((p) => (
              <li key={p.label} className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{p.label}</p>
                  <p className="text-sm text-ink-3">{p.hint}</p>
                </div>
                <Button onClick={() => fire.mutate(p)} disabled={fire.isPending || !can("operator")}>
                  Send
                </Button>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={!!t?.enabled}
                disabled={!can("operator") || !t}
                onChange={(e) => setTraffic.mutate({ enabled: e.target.checked, rate_per_min: t?.rate_per_min ?? 4 })}
              />
              Live traffic
            </label>
            <label className="flex items-center gap-2">
              <span className="text-ink-3">events per minute</span>
              <select
                value={t?.rate_per_min ?? 4}
                disabled={!can("operator")}
                onChange={(e) => setTraffic.mutate({ enabled: !!t?.enabled, rate_per_min: Number(e.target.value) })}
                className="rounded border border-line bg-paper px-2 py-1"
              >
                {[2, 4, 6, 10, 20].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
        </Section>
        <Section title="Website chat">{slug && <ChatSim key={slug} slug={slug} />}</Section>
        <Section title="Phone (Twilio)">{slug && <PhoneSim key={slug} slug={slug} />}</Section>
        <Section title="Email">{slug && <EmailSim key={slug} slug={slug} />}</Section>
      </div>
    </>
  );
}
