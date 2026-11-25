import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, ChevronLeft, ChevronRight, Clock, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button, cx, Empty, ErrorNote, Kbd, Segmented, Skeleton, Toolbar } from "@/components/ui";
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

function Decision({ a, onDecided, onBack }: { a: Approval; onDecided: () => void; onBack: () => void }) {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const allowed = can(a.min_role as "operator" | "admin" | "owner");
  const pending = a.status === "pending";
  const decide = useMutation({
    mutationFn: (approved: boolean) => api.post<Approval>(`/api/approvals/${a.id}/decision`, { approved, comment: comment || null }),
    onSuccess: (res) => {
      toast(res.status === "approved" ? "Approved — the agent is continuing." : "Rejected — the agent will continue without it.");
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
      onDecided();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        toast("Someone else already decided this one.");
        qc.invalidateQueries({ queryKey: ["approvals"] });
      } else toast((e as Error).message, "error");
    },
  });

  // A and R decide, when this person is allowed to.
  useEffect(() => {
    if (!pending) return;
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
  }, [pending, allowed, decide]);

  const amount = headline(a);
  return (
    <section aria-label="Decision" className="flex min-w-0 flex-1 flex-col">
      <Toolbar
        leading={
          <button onClick={onBack} className="-ml-1 flex items-center text-[13px] text-accent lg:hidden" aria-label="Back to requests">
            <ChevronLeft size={18} /> Approvals
          </button>
        }
      />
      <div key={a.id} className="min-h-0 flex-1 animate-[fade_180ms_ease-out] overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 pt-10 pb-12">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-3">
            <span className="flex items-center gap-1.5">
              <Clock size={12} aria-hidden /> Requested {ago(a.requested_at)}
            </span>
            {a.escalation_level > 0 && <span className="font-medium text-hold">Escalated {a.escalation_level}×</span>}
            {!pending && (
              <span className={cx("font-medium", a.status === "approved" ? "text-clear" : "text-ink-2")}>
                {humanize(a.status)}
                {a.comment ? `: ${a.comment}` : ""}
              </span>
            )}
          </div>
          <h2 className="mt-3 text-[26px] leading-tight font-semibold tracking-[-0.022em] text-balance">{a.description}</h2>
          {amount && <p className="mt-4 font-figure text-[56px] text-ink">{amount}</p>}

          <div className="mt-6 overflow-hidden rounded-xl bg-group shadow-[inset_0_0_0_0.5px_var(--line)]">
            <p className="px-4 pt-3 pb-1 text-[11.5px] font-semibold text-ink-3">Why a person has to decide</p>
            <ul>
              {a.risk_reasons.map((r) => (
                <li key={r} className="flex items-start gap-2.5 px-4 py-2 text-[13px] text-ink-2">
                  <ShieldAlert size={14} className="mt-0.5 shrink-0 text-hold" aria-hidden />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
            <Link
              to={`/runs/${a.run_id}`}
              className="flex items-center justify-between border-t border-line/70 px-4 py-2.5 text-[13px] text-ink hover:bg-fill"
            >
              <span className="truncate">{a.run_title ?? "View run"}</span>
              <ChevronRight size={14} className="shrink-0 text-ink-3" aria-hidden />
            </Link>
          </div>

          {pending ? (
            <div className="mt-6">
              <label className="text-[12px] text-ink-3" htmlFor={`c-${a.id}`}>
                Note for the record (optional)
              </label>
              <textarea
                id={`c-${a.id}`}
                rows={2}
                placeholder="Why you decided"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="field mt-1.5 w-full resize-none"
              />
              <div className="mt-4 flex flex-wrap items-center gap-2.5">
                <Button size="lg" variant="primary" className="min-w-36" disabled={!allowed || decide.isPending} onClick={() => decide.mutate(true)}>
                  <Check size={16} aria-hidden /> Approve
                </Button>
                <Button size="lg" variant="danger" className="min-w-28" disabled={!allowed || decide.isPending} onClick={() => decide.mutate(false)}>
                  <X size={16} aria-hidden /> Reject
                </Button>
                {allowed ? (
                  <span className="ml-auto hidden items-center gap-1.5 text-[12px] text-ink-3 sm:flex">
                    <Kbd>A</Kbd> approve <Kbd>R</Kbd> reject
                  </span>
                ) : (
                  <p className="w-full text-[13px] text-ink-3">Needs {ROLE_PHRASE[a.min_role] ?? a.min_role} to decide.</p>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default function Approvals() {
  const { tenant } = useAuth();
  const navigate = useNavigate();
  const { approvalId } = useParams();
  const [view, setView] = useState<"pending" | "all">("pending");
  const q = useQuery({
    queryKey: ["approvals", view, tenant?.tenant_id],
    queryFn: () => api.get<Approval[]>("/api/approvals", { status: view === "pending" ? "pending" : undefined }),
  });
  const items = q.data ?? [];
  const index = Math.max(
    0,
    items.findIndex((a) => a.id === approvalId),
  );
  const current = items[index];
  const open = (a: Approval) => navigate(`/approvals/${a.id}`, { replace: !!approvalId });

  useEffect(() => {
    document.title = "Approvals · Oryn OS";
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      const move = (d: number) => {
        e.preventDefault();
        const next = items[Math.min(Math.max(index + d, 0), items.length - 1)];
        if (next) open(next);
      };
      if (e.key === "j" || e.key === "ArrowDown") move(1);
      if (e.key === "k" || e.key === "ArrowUp") move(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // After a decision the next request takes its place, the way an inbox moves on.
  const onDecided = () => {
    const next = items[index + 1] ?? items[index - 1];
    navigate(next && next.id !== current?.id ? `/approvals/${next.id}` : "/approvals", { replace: true });
  };

  return (
    <>
      <section aria-label="Requests" className={cx("flex min-h-0 w-full shrink-0 flex-col border-r border-line/80 lg:w-[360px]", approvalId && "hidden lg:flex")}>
        <Toolbar title="Approvals" local />
        <div className="border-b border-line/70 px-3 py-2.5">
          <Segmented
            label="Show"
            value={view}
            onChange={(v) => {
              setView(v);
              navigate("/approvals", { replace: true });
            }}
            options={[
              { value: "pending", label: view === "pending" && q.data ? `Waiting ${items.length}` : "Waiting" },
              { value: "all", label: "History" },
            ]}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto py-1.5">
          <ErrorNote error={q.error} />
          {q.isLoading ? (
            <div className="space-y-2 px-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-[72px]" />
              ))}
            </div>
          ) : items.length ? (
            <ul aria-label="Approval requests" className="space-y-px">
              {items.map((a) => {
                const on = a.id === current?.id;
                const amount = headline(a);
                return (
                  <li
                    key={a.id}
                    onClick={() => open(a)}
                    aria-current={on ? "true" : undefined}
                    className={cx("mx-2 cursor-default rounded-lg px-3 py-2.5 select-none", on ? "bg-select text-white" : "hover:bg-fill")}
                  >
                    <div className="flex items-baseline gap-2">
                      <span className={cx("h-2 w-2 shrink-0 translate-y-[-1px] rounded-full", a.status === "pending" ? "bg-hold" : a.status === "approved" ? "bg-clear" : "bg-idle")} aria-hidden />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{a.description}</span>
                      {amount && <span className={cx("shrink-0 font-figure text-[13px]", on ? "text-white" : "text-ink")}>{amount}</span>}
                    </div>
                    <div className={cx("mt-0.5 flex gap-2 pl-4 text-[12px]", on ? "text-white/80" : "text-ink-3")}>
                      <span className="min-w-0 flex-1 truncate">{a.run_title}</span>
                      <span className="shrink-0">{ago(a.requested_at)}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Empty title={view === "pending" ? "You're all caught up" : "No approvals yet"}>When an agent proposes something above your limits, it waits here.</Empty>
          )}
        </div>
      </section>

      {current ? (
        <Decision key={current.id} a={current} onDecided={onDecided} onBack={() => navigate("/approvals")} />
      ) : (
        <div className="hidden min-w-0 flex-1 flex-col lg:flex">
          <Toolbar />
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-clear/12 text-clear">
              <CheckCircle2 size={28} strokeWidth={1.7} />
            </span>
            <p className="text-[15px] font-semibold">Nothing waiting on you</p>
            <p className="max-w-[30ch] text-[13px] text-ink-3">Agents pause here before discounts, refunds and large amounts. Nothing happens until a person decides.</p>
          </div>
        </div>
      )}
    </>
  );
}
