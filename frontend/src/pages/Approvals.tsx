import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Check, Clock, ShieldAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, cx, Empty, ErrorNote, Kbd, PageHeader, Segmented, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ago, humanize, usd } from "@/lib/format";

type Approval = S["ApprovalOut"];
const ROLE_PHRASE: Record<string, string> = {
  operator: "an operator, admin or owner",
  admin: "an admin or owner",
  owner: "an owner",
};

/** The one number a person is really being asked about, when there is one. */
function headline(a: Approval): string | null {
  const args = a.action_args as Record<string, unknown>;
  if (args.amount_usd !== undefined) return usd(Number(args.amount_usd), 2);
  if (args.discount_pct !== undefined) return `${args.discount_pct}% off`;
  return null;
}

function ApprovalItem({ a, selected, onSelect }: { a: Approval; selected: boolean; onSelect: () => void }) {
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
      qc.invalidateQueries({ queryKey: ["metrics"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        toast("Someone else already decided this one.");
        qc.invalidateQueries({ queryKey: ["approvals"] });
      } else toast((e as Error).message, "error");
    },
  });
  const pending = a.status === "pending";
  const amount = headline(a);
  const card = useRef<HTMLLIElement>(null);

  // A and R decide the selected approval, when this person is allowed to.
  useEffect(() => {
    if (!selected || !pending) return;
    card.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (document.querySelector('[aria-modal="true"]') || !allowed || decide.isPending) return;
      if (e.key === "a") {
        e.preventDefault();
        decide.mutate(true);
      }
      if (e.key === "r") {
        e.preventDefault();
        decide.mutate(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, pending, allowed, decide]);

  return (
    <li
      ref={card}
      onMouseDown={onSelect}
      className={cx(
        "card transition-[box-shadow,opacity] duration-200",
        selected && pending && "shadow-[0_0_0_2px_var(--accent),0_8px_24px_-8px_rgb(0_0_0/0.15)]",
        decide.isPending && "opacity-60",
      )}
    >
      <div className="grid gap-6 p-6 md:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-3">
            <span className="flex items-center gap-1.5">
              <Clock size={13} aria-hidden /> Requested {ago(a.requested_at)}
            </span>
            {a.escalation_level > 0 && <span className="font-medium text-hold">Escalated {a.escalation_level}×</span>}
            {!pending && (
              <span className={cx("font-medium", a.status === "approved" ? "text-clear" : "text-ink-2")}>
                {humanize(a.status)}
                {a.comment ? `: ${a.comment}` : ""}
              </span>
            )}
          </div>
          <p className="mt-2 font-display text-[22px] leading-snug">{a.description}</p>
          {amount && <p className="mt-3 font-figure text-[44px] text-ink">{amount}</p>}
          <ul className="mt-4 space-y-1.5">
            {a.risk_reasons.map((r) => (
              <li key={r} className="flex items-start gap-2 text-sm text-ink-2">
                <ShieldAlert size={15} className="mt-0.5 shrink-0 text-hold" aria-hidden />
                <span>{r}</span>
              </li>
            ))}
          </ul>
          <Link to={`/runs/${a.run_id}`} className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-ink-2 hover:text-accent">
            {a.run_title ?? "View run"} <ArrowUpRight size={14} aria-hidden />
          </Link>
        </div>

        {pending && (
          <div className="flex flex-col gap-2.5 md:border-l md:border-line/70 md:pl-6">
            <label className="text-[13px] text-ink-3" htmlFor={`c-${a.id}`}>
              Note for the record (optional)
            </label>
            <textarea
              id={`c-${a.id}`}
              rows={2}
              placeholder="Why you decided"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="field resize-none"
            />
            <div className="mt-1 grid grid-cols-2 gap-2">
              <Button variant="danger" disabled={!allowed || decide.isPending} onClick={() => decide.mutate(false)}>
                <X size={15} aria-hidden /> Reject
              </Button>
              <Button variant="primary" disabled={!allowed || decide.isPending} onClick={() => decide.mutate(true)}>
                <Check size={15} aria-hidden /> Approve
              </Button>
            </div>
            {allowed ? (
              selected && (
                <p className="flex items-center justify-center gap-1.5 text-xs text-ink-3">
                  <Kbd>A</Kbd> approve <Kbd>R</Kbd> reject
                </p>
              )
            ) : (
              <p className="text-sm text-ink-3">Needs {ROLE_PHRASE[a.min_role] ?? a.min_role} to decide.</p>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

export default function Approvals() {
  const { tenant } = useAuth();
  const [view, setView] = useState<"pending" | "all">("pending");
  const [sel, setSel] = useState(0);
  const q = useQuery({
    queryKey: ["approvals", view, tenant?.tenant_id],
    queryFn: () => api.get<Approval[]>("/api/approvals", { status: view === "pending" ? "pending" : undefined }),
  });
  const items = q.data ?? [];
  const waiting = view === "pending" ? items.length : null;
  // Clamp instead of resetting in an effect: deciding the last card moves the focus up one.
  const current = Math.min(sel, Math.max(items.length - 1, 0));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      if (e.key === "j") {
        e.preventDefault();
        setSel((s) => Math.min(s + 1, items.length - 1));
      }
      if (e.key === "k") {
        e.preventDefault();
        setSel((s) => Math.max(Math.min(s, items.length - 1) - 1, 0));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items.length]);

  return (
    <>
      <PageHeader
        title="Approvals"
        sub="Agents pause here before anything risky: discounts, refunds, large amounts. Nothing happens until a person decides."
        actions={
          <Segmented
            label="Show"
            value={view}
            onChange={(v) => (setView(v), setSel(0))}
            options={[
              { value: "pending", label: waiting === null ? "Waiting" : `Waiting ${waiting}` },
              { value: "all", label: "History" },
            ]}
          />
        }
      />
      <ErrorNote error={q.error} />
      {q.isLoading ? (
        <Skeleton className="h-56" />
      ) : items.length ? (
        <ul aria-label="Approval requests" className="grid gap-4">
          {items.map((a, i) => (
            <ApprovalItem key={a.id} a={a} selected={i === current} onSelect={() => setSel(i)} />
          ))}
        </ul>
      ) : (
        <div className="card">
          <Empty title={view === "pending" ? "You're all caught up" : "No approvals yet"}>
            When an agent proposes something above your policy limits, it waits here for a decision.
          </Empty>
        </div>
      )}
    </>
  );
}
