import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { S } from "@/api/client";
import { cx } from "@/components/ui";
import { useNow } from "@/hooks/useNow";
import { ago, cost, duration } from "@/lib/format";
import { statusOf } from "@/lib/status";

/** A run as a flight strip: status edge, route of agents that held it, timing and cost. */
export function RunStrip({ run }: { run: S["RunOut"] }) {
  const st = statusOf(run.status);
  const live = run.status === "running" || run.status === "waiting_approval";
  const now = useNow(live ? 1000 : null);
  const elapsed = run.duration_s ?? (now - new Date(run.started_at).getTime()) / 1000;
  return (
    <Link
      to={`/runs/${run.id}`}
      className="group grid grid-cols-[6px_1fr_auto] overflow-hidden rounded-md border border-line bg-panel hover:border-ink-3"
    >
      <span className={st.color} aria-hidden />
      <span className="min-w-0 px-3 py-2">
        <span className="flex items-baseline gap-2">
          <span className="truncate font-display text-[17px] font-semibold">{run.title || "Untitled run"}</span>
          <span className={cx("shrink-0 text-sm font-medium", st.text)}>{st.label}</span>
        </span>
        <span className="mt-0.5 flex items-center gap-1 text-sm text-ink-3">
          {run.route.length ? (
            run.route.map((agent, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <ChevronRight size={13} aria-hidden />}
                <span className={cx(i === run.route.length - 1 && live && "text-ink")}>{agent}</span>
              </span>
            ))
          ) : (
            <span>{run.kind === "conversation" ? "Conversation" : "Waiting for an agent"}</span>
          )}
        </span>
      </span>
      <span className="flex flex-col items-end justify-center px-3 py-2 text-sm">
        <span className="font-medium">{duration(elapsed)}</span>
        <span className="text-xs text-ink-3">
          {Number(run.total_cost_usd) > 0 ? cost(run.total_cost_usd) : ago(run.started_at)}
        </span>
      </span>
    </Link>
  );
}
