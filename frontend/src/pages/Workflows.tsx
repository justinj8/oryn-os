import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Empty, ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import { ago, num } from "@/lib/format";

export default function Workflows() {
  const { can, tenant } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["workflows", tenant?.tenant_id], queryFn: () => api.get<S["WorkflowOut"][]>("/api/workflows") });
  const toggle = useMutation({
    mutationFn: (w: S["WorkflowOut"]) => api.patch(`/api/workflows/${w.id}`, { enabled: !w.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
  return (
    <>
      <PageHeader
        title="Workflows"
        sub="What happens when an event arrives. Describe a workflow in plain English and Oryn builds it."
        actions={
          can("admin") && (
            <Link to="/workflows/new" className="inline-flex items-center gap-1.5 rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-paper hover:bg-ink-2">
              <Plus size={15} aria-hidden /> New workflow
            </Link>
          )
        }
      />
      <ErrorNote error={q.error} />
      {q.isLoading ? (
        <Skeleton className="h-40" />
      ) : q.data?.length ? (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-sm">
            <thead className="text-left text-ink-3">
              <tr>
                <th className="px-4 py-2 font-normal">Workflow</th>
                <th className="px-4 py-2 font-normal">Starts when</th>
                <th className="px-4 py-2 text-right font-normal">Version</th>
                <th className="px-4 py-2 text-right font-normal">Runs</th>
                <th className="px-4 py-2 font-normal">Updated</th>
                <th className="px-4 py-2 font-normal">On</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((w) => (
                <tr key={w.id} className="border-t border-line">
                  <td className="px-4 py-2.5">
                    <Link to={`/workflows/${w.id}`} className="font-medium hover:text-flight">
                      {w.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5">
                    <code className="text-ink-2">{w.trigger_event}</code>
                  </td>
                  <td className="px-4 py-2.5 text-right">v{w.current_version}</td>
                  <td className="px-4 py-2.5 text-right">{num(w.runs_total)}</td>
                  <td className="px-4 py-2.5 text-ink-3">{ago(w.updated_at)}</td>
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      aria-label={`${w.enabled ? "Turn off" : "Turn on"} ${w.name}`}
                      checked={w.enabled}
                      disabled={!can("admin")}
                      onChange={() => toggle.mutate(w)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="No workflows yet">Create one by describing it — for example, “When a new lead arrives, have the sales agent qualify it.”</Empty>
      )}
    </>
  );
}
