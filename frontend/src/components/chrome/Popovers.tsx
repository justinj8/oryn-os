import { useQuery } from "@tanstack/react-query";
import { Bell, CheckCircle2, CircleAlert, Hand, Route, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { cx, Empty, Skeleton } from "@/components/ui";
import { ago, usd } from "@/lib/format";

/** A toolbar popover: opens under its button, closes on Escape, outside click or navigation. */
function Popover({ button, children, label }: { button: (open: boolean) => ReactNode; children: (close: () => void) => ReactNode; label: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <div onClick={() => setOpen((o) => !o)}>{button(open)}</div>
      {open && (
        <div
          role="dialog"
          aria-label={label}
          className="material absolute top-full right-0 z-40 mt-2 w-[min(400px,calc(100vw-24px))] origin-top-right animate-[pop_220ms_var(--ease-spring)] overflow-hidden rounded-[18px] shadow-[var(--pop-shadow)]"
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

// ---- activity -----------------------------------------------------------------------------------

type Item = S["ActivityItem"];
const KIND: Record<Item["kind"], { icon: LucideIcon; tint: string }> = {
  approval_requested: { icon: Hand, tint: "bg-hold" },
  approval_decided: { icon: ShieldCheck, tint: "bg-clear" },
  run_failed: { icon: CircleAlert, tint: "bg-fail" },
  run_escalated: { icon: Route, tint: "bg-divert" },
  outcome: { icon: Sparkles, tint: "bg-accent" },
};

const seenKey = (tenant: string | undefined) => `oryn.activity.seen.${tenant ?? "none"}`;
function readSeen(tenant: string | undefined): number {
  try {
    return Number(localStorage.getItem(seenKey(tenant)) ?? 0);
  } catch {
    return 0;
  }
}

export function useActivity(limit = 30) {
  const { tenant } = useAuth();
  return useQuery({
    queryKey: ["activity", tenant?.tenant_id, limit],
    queryFn: () => api.get<Item[]>("/api/activity", { limit }),
    enabled: !!tenant,
    refetchInterval: 60_000,
  });
}

export function ActivityList({ items, seenAt = Infinity, onNavigate }: { items: Item[]; seenAt?: number; onNavigate?: () => void }) {
  return (
    <ul className="divide-y divide-line/70">
      {items.map((i) => {
        const k = KIND[i.kind];
        const unread = new Date(i.at).getTime() > seenAt;
        return (
          <li key={i.id}>
            <Link to={i.href} onClick={onNavigate} className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-sunk/70 active:bg-sunk">
              <span className={cx("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white", k.tint)} aria-hidden>
                <k.icon size={14} strokeWidth={2.2} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-[14px] font-medium text-ink">{i.title}</span>
                  <span className="shrink-0 text-[12px] text-ink-3">{ago(i.at)}</span>
                </span>
                <span className="mt-0.5 flex items-center gap-2 text-[13px] text-ink-3">
                  <span className="truncate">{i.detail}</span>
                  {i.value_usd ? <span className="shrink-0 font-medium text-clear">{usd(i.value_usd)}</span> : null}
                </span>
              </span>
              {unread && <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent" aria-label="New" />}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function ActivityButton() {
  const { tenant } = useAuth();
  const tid = tenant?.tenant_id;
  const q = useActivity();
  const [seenAt, setSeenAt] = useState(() => readSeen(tid));
  const [shownSeen, setShownSeen] = useState(seenAt);
  const items = q.data ?? [];
  const unread = items.filter((i) => new Date(i.at).getTime() > seenAt).length;

  const markSeen = () => {
    const now = Date.now();
    setShownSeen(seenAt); // keep the blue dots visible while the panel is open
    setSeenAt(now);
    try {
      localStorage.setItem(seenKey(tid), String(now));
    } catch {
      /* private mode: unread state lasts for this page only */
    }
  };

  return (
    <Popover
      label="Activity"
      button={(open) => (
        <button
          onClick={() => !open && markSeen()}
          aria-label={unread ? `Activity, ${unread} new` : "Activity"}
          className={cx("relative flex h-9 w-9 items-center justify-center rounded-full text-ink-2 transition-colors hover:bg-sunk hover:text-ink", open && "bg-sunk text-ink")}
        >
          <Bell size={18} strokeWidth={1.9} />
          {unread > 0 && (
            <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-fail px-1 text-[10px] font-semibold text-white ring-2 ring-paper">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      )}
    >
      {(close) => (
        <>
          <div className="flex items-center justify-between px-4 pt-4 pb-2">
            <h2 className="text-[17px] font-semibold tracking-[-0.022em]">Activity</h2>
            <span className="text-[12px] text-ink-3">Failures, decisions and outcomes</span>
          </div>
          <div className="max-h-[min(70vh,520px)] overflow-y-auto pb-1">
            {q.isLoading ? (
              <div className="p-4">
                <Skeleton className="h-24" />
              </div>
            ) : items.length ? (
              <ActivityList items={items} seenAt={shownSeen} onNavigate={close} />
            ) : (
              <Empty title="Nothing to report">Failures, approvals and outcomes show up here as they happen.</Empty>
            )}
          </div>
        </>
      )}
    </Popover>
  );
}

// ---- system status ------------------------------------------------------------------------------

export function StatusButton() {
  const { tenant } = useAuth();
  const q = useQuery({
    queryKey: ["system-status", tenant?.tenant_id],
    queryFn: () => api.get<S["SystemStatus"]>("/api/system/status"),
    enabled: !!tenant,
    refetchInterval: 30_000,
  });
  const d = q.data;
  const issues = d?.checks.filter((c) => !c.ok) ?? [];
  const tone = !d ? "bg-idle" : d.ok ? "bg-clear" : "bg-hold";
  const label = !d ? "Checking systems" : d.ok ? "All systems normal" : `${issues.length} ${issues.length === 1 ? "issue" : "issues"}`;
  return (
    <Popover
      label="System status"
      button={(open) => (
        <button
          aria-label={`System status: ${label}`}
          className={cx("flex h-9 items-center gap-2 rounded-full px-3 text-[13px] text-ink-2 transition-colors hover:bg-sunk hover:text-ink", open && "bg-sunk text-ink")}
        >
          <span className={cx("h-2 w-2 rounded-full", tone)} aria-hidden />
          <span className="hidden lg:inline">{label}</span>
        </button>
      )}
    >
      {() => (
        <div className="p-4">
          <div className="mb-3 flex items-center gap-3">
            <span className={cx("flex h-9 w-9 items-center justify-center rounded-full text-white", d?.ok ? "bg-clear" : "bg-hold")} aria-hidden>
              {d?.ok ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}
            </span>
            <div>
              <h2 className="text-[17px] font-semibold tracking-[-0.022em]">{label}</h2>
              <p className="text-[12px] text-ink-3">
                {d ? `Checked ${ago(d.checked_at)}. Model provider: ${d.llm_provider === "replay" ? "offline replay" : "Claude"}.` : "Asking each service…"}
              </p>
            </div>
          </div>
          <ul className="card overflow-hidden">
            {(d?.checks ?? []).map((c, i) => (
              <li key={c.name} className={cx("flex items-start gap-3 px-4 py-3", i > 0 && "border-t border-line/70")}>
                <span className={cx("mt-1.5 h-2 w-2 shrink-0 rounded-full", c.ok ? "bg-clear" : "bg-fail")} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="text-[14px] font-medium">{c.name}</span>
                    <span className="text-[12px] text-ink-3 tabular-nums">{c.latency_ms.toFixed(0)} ms</span>
                  </span>
                  <span className="block text-[13px] text-ink-3">{c.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Popover>
  );
}
