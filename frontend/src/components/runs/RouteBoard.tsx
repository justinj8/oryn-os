import { Check, Hand, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { S } from "@/api/client";
import { cx, StatusDot } from "@/components/ui";
import { useNow } from "@/hooks/useNow";
import { ago, cost, duration } from "@/lib/format";
import { statusOf } from "@/lib/status";

type Run = S["RunOut"];

/**
 * A run drawn as its route: one stop per agent that held it. While it runs, a signal travels the open
 * segment after the current agent; while it waits on a person, the signal stops at a hold marker.
 */
export function RunRoute({ run, compact }: { run: Run; compact?: boolean }) {
  const stops = run.route.length ? run.route : [run.kind === "conversation" ? "Conversation" : "Starting"];
  const running = run.status === "running";
  const waiting = run.status === "waiting_approval";
  const done = run.status === "completed";
  const failed = run.status === "failed" || run.status === "cancelled";
  return (
    <div className="flex min-w-0 items-center" aria-label={`Route: ${stops.join(" to ")}`}>
      {stops.map((agent, i) => {
        const last = i === stops.length - 1;
        return (
          <div key={i} className={cx("flex min-w-0 items-center", !last && "flex-1")}>
            <span className="flex min-w-0 shrink items-center gap-1.5">
              <span
                className={cx(
                  "h-2.5 w-2.5 shrink-0 rounded-full border-2",
                  last && running ? "border-accent bg-accent beacon" : last && waiting ? "border-hold bg-hold" : "border-ink-3/70 bg-panel",
                )}
                aria-hidden
              />
              <span className={cx("truncate text-[13px]", last && (running || waiting) ? "font-medium text-ink" : "text-ink-3")}>{agent}</span>
            </span>
            {!last && <span className="mx-2 h-px min-w-4 flex-1 bg-line-2" aria-hidden />}
          </div>
        );
      })}
      {!compact && (running || waiting) && (
        <span className="relative mx-2 h-px min-w-10 flex-1 overflow-visible" aria-hidden>
          <span className={cx("absolute inset-0", waiting ? "border-t border-dashed border-hold/60" : "bg-gradient-to-r from-accent/50 to-transparent")} />
          {running && (
            <span className="absolute top-1/2 left-0 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-accent shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_20%,transparent)] [animation:signal_1.8s_var(--ease-out)_infinite]" />
          )}
        </span>
      )}
      {waiting && (
        <span className="ml-0.5 inline-flex shrink-0 items-center gap-1 rounded-full bg-hold/12 px-2 py-0.5 text-xs font-medium text-hold">
          <Hand size={12} aria-hidden /> Waiting on a person
        </span>
      )}
      {done && (
        <span className="ml-2 inline-flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-clear text-white" aria-hidden>
          <Check size={11} strokeWidth={3} />
        </span>
      )}
      {failed && (
        <span className="ml-2 inline-flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-fail/90 text-white" aria-hidden>
          <X size={11} strokeWidth={3} />
        </span>
      )}
    </div>
  );
}

export function RouteRow({ run }: { run: Run }) {
  const st = statusOf(run.status);
  const live = run.status === "running" || run.status === "waiting_approval";
  const now = useNow(live ? 1000 : null);
  const elapsed = run.duration_s ?? (now - new Date(run.started_at).getTime()) / 1000;
  return (
    <Link
      to={`/runs/${run.id}`}
      className="group grid grid-cols-1 items-center gap-x-6 gap-y-2 px-5 py-4 transition-colors hover:bg-sunk/60 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_88px]"
    >
      <span className="min-w-0">
        <span className="flex items-center gap-2">
          <StatusDot status={run.status} />
          <span className="truncate text-[15px] font-medium text-ink">{run.title || "Untitled run"}</span>
        </span>
        <span className="mt-0.5 block pl-4 text-[13px] text-ink-3">
          {st.label}, started {ago(run.started_at)}
        </span>
      </span>
      <RunRoute run={run} />
      <span className="text-left sm:text-right">
        <span className="block font-figure text-[19px] text-ink">{duration(elapsed)}</span>
        <span className="block text-xs text-ink-3">{Number(run.total_cost_usd) > 0 ? cost(run.total_cost_usd) : "no model cost"}</span>
      </span>
    </Link>
  );
}
