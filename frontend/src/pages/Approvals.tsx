import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, cx, Empty, ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ago, humanize, usd } from "@/lib/format";

type Approval = S["ApprovalOut"];
const ROLE_PHRASE: Record<string, string> = {
  operator: "an operator, admin or owner",
  admin: "an admin or owner",
  owner: "an owner",
};

function Args({ a }: { a: Approval }) {
  const args = a.action_args as Record<string, unknown>;
  const money = args.amount_usd !== undefined ? usd(Number(args.amount_usd), 2) : args.discount_pct !== undefined ? `${args.discount_pct}% discount` : null;
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
      {money && <span className="font-display text-2xl font-semibold">{money}</span>}
      {a.action_tool && <code className="text-ink-3">{a.action_tool}</code>}
    </div>
  );
}

function ApprovalItem({ a }: { a: Approval }) {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const allowed = can(a.min_role as "operator" | "admin" | "owner");
  const decide = useMutation({
    mutationFn: (approved: boolean) => api.post<Approval>(`/api/approvals/${a.id}/decision`, { approved, comment: comment || null }),
    onSuccess: (res) => {
      toast(res.status === "approved" ? "Approved — the agent is continuing." : "Rejected — the agent will continue without it.");
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        toast("Someone else already decided this one.");
        qc.invalidateQueries({ queryKey: ["approvals"] });
      } else toast((e as Error).message, "error");
    },
  });
  const pending = a.status === "pending";
  return (
    <li className={cx("grid grid-cols-[6px_1fr] overflow-hidden rounded-md border border-line bg-panel", !pending && "opacity-80")}>
      <span className={pending ? "bg-hold" : a.status === "approved" ? "bg-clear" : "bg-idle"} aria-hidden />
      <div className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-display text-xl font-semibold">{a.description}</p>
            <Link to={`/runs/${a.run_id}`} className="text-sm text-flight hover:underline">
              {a.run_title ?? "View run"}
            </Link>
          </div>
          <p className="text-right text-sm text-ink-3">
            Requested {ago(a.requested_at)}
            {a.escalation_level > 0 && <span className="block text-hold">Escalated {a.escalation_level}×</span>}
          </p>
        </div>
        <div className="mt-3">
          <Args a={a} />
        </div>
        <ul className="mt-2 list-disc pl-5 text-sm text-ink-2">
          {a.risk_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        {pending ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor={`c-${a.id}`}>
              Comment
            </label>
            <input
              id={`c-${a.id}`}
              placeholder="Comment (optional)"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-line bg-paper px-3 py-1.5 text-sm"
            />
            <Button variant="primary" disabled={!allowed || decide.isPending} onClick={() => decide.mutate(true)}>
              Approve
            </Button>
            <Button variant="danger" disabled={!allowed || decide.isPending} onClick={() => decide.mutate(false)}>
              Reject
            </Button>
            {!allowed && <p className="w-full text-sm text-ink-3">Needs {ROLE_PHRASE[a.min_role] ?? a.min_role} to decide.</p>}
          </div>
        ) : (
          <p className="mt-3 text-sm text-ink-3">
            {humanize(a.status)}
            {a.comment ? `: ${a.comment}` : ""}
          </p>
        )}
      </div>
    </li>
  );
}

export default function Approvals() {
  const { tenant } = useAuth();
  const [view, setView] = useState<"pending" | "all">("pending");
  const q = useQuery({
    queryKey: ["approvals", view, tenant?.tenant_id],
    queryFn: () => api.get<Approval[]>("/api/approvals", { status: view === "pending" ? "pending" : undefined }),
  });
  return (
    <>
      <PageHeader
        title="Approvals"
        sub="Agents pause here before anything risky — discounts, refunds, large amounts. Nothing happens until someone decides."
        actions={
          <div className="inline-flex rounded-md border border-line bg-panel p-0.5 text-sm">
            {(["pending", "all"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} className={cx("rounded px-2.5 py-1", view === v ? "bg-ink text-paper" : "text-ink-2")}>
                {v === "pending" ? "Waiting" : "History"}
              </button>
            ))}
          </div>
        }
      />
      <ErrorNote error={q.error} />
      {q.isLoading ? (
        <Skeleton className="h-40" />
      ) : q.data?.length ? (
        <ul className="grid gap-3">
          {q.data.map((a) => (
            <ApprovalItem key={a.id} a={a} />
          ))}
        </ul>
      ) : (
        <Empty title={view === "pending" ? "Nothing waiting for you" : "No approvals yet"}>
          When an agent proposes something above your policy limits, it shows up here.
        </Empty>
      )}
    </>
  );
}
