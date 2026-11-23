import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { ChatSim } from "@/components/sim/ChatSim";
import { EmailSim } from "@/components/sim/EmailSim";
import { PhoneSim } from "@/components/sim/PhoneSim";
import { Button, PageHeader, Section, Switch } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { PRESETS } from "@/lib/presets";

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
            <Link to="/" className="text-accent hover:underline">
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
            <Switch
              showLabel
              label="Live traffic"
              checked={!!t?.enabled}
              disabled={!can("operator") || !t}
              onChange={(enabled) => setTraffic.mutate({ enabled, rate_per_min: t?.rate_per_min ?? 4 })}
            />
            <label className="flex items-center gap-2">
              <span className="text-ink-3">events per minute</span>
              <select
                value={t?.rate_per_min ?? 4}
                disabled={!can("operator")}
                onChange={(e) => setTraffic.mutate({ enabled: !!t?.enabled, rate_per_min: Number(e.target.value) })}
                className="field"
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
