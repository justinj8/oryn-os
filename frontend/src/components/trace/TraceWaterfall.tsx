import { Bot, Brain, CircleAlert, Clock, GitBranch, Hand, Mail, RotateCcw, Route, Wrench, type LucideIcon } from "lucide-react";
import type { S } from "@/api/client";
import { cx } from "@/components/ui";
import { useNow } from "@/hooks/useNow";
import { cost, duration } from "@/lib/format";

export type SpanLike = S["SpanOut"];
export type SpanRow = { span: SpanLike; depth: number };

export const KIND: Record<string, { icon: LucideIcon; label: string; bar: string }> = {
  run: { icon: Route, label: "Run", bar: "bg-ink-3" },
  agent: { icon: Bot, label: "Agent", bar: "bg-ink-2" },
  llm_call: { icon: Brain, label: "Model call", bar: "bg-flight" },
  tool_call: { icon: Wrench, label: "Tool call", bar: "bg-clear" },
  handoff: { icon: GitBranch, label: "Handoff", bar: "bg-divert" },
  approval: { icon: Hand, label: "Approval", bar: "bg-hold" },
  decision: { icon: GitBranch, label: "Decision", bar: "bg-ink-3" },
  retry: { icon: RotateCcw, label: "Retry", bar: "bg-fail" },
  error: { icon: CircleAlert, label: "Error", bar: "bg-fail" },
  notify: { icon: Mail, label: "Notification", bar: "bg-clear" },
  wait: { icon: Clock, label: "Wait", bar: "bg-ink-3" },
};

/** Depth-first, start-ordered rows: children appear directly under their parent. */
export function buildSpanTree(spans: SpanLike[]): SpanRow[] {
  const ids = new Set(spans.map((s) => s.id));
  const byParent = new Map<string | null, SpanLike[]>();
  for (const s of spans) {
    const parent = s.parent_span_id && ids.has(s.parent_span_id) ? s.parent_span_id : null;
    byParent.set(parent, [...(byParent.get(parent) ?? []), s]);
  }
  const at = (s: SpanLike) => new Date(s.started_at).getTime();
  const rows: SpanRow[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const s of (byParent.get(parent) ?? []).sort((a, b) => at(a) - at(b))) {
      rows.push({ span: s, depth });
      walk(s.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

const ms = (iso: string) => new Date(iso).getTime();

export function TraceWaterfall({ spans, onSelect, selectedId }: { spans: SpanLike[]; onSelect: (s: SpanLike) => void; selectedId?: string }) {
  const rows = buildSpanTree(spans);
  const running = spans.some((s) => !s.ended_at);
  const now = useNow(running ? 1000 : null);
  if (!rows.length) return null;
  const t0 = Math.min(...spans.map((s) => ms(s.started_at)));
  const t1 = Math.max(...spans.map((s) => (s.ended_at ? ms(s.ended_at) : Math.min(now, ms(s.started_at) + 1000))));
  const total = Math.max(t1 - t0, 1);

  return (
    <div className="overflow-x-auto">
      <ol className="min-w-[640px]" aria-label="Execution trace">
        {rows.map(({ span: s, depth }) => {
          const k = KIND[s.kind] ?? KIND.decision;
          const start = ms(s.started_at);
          const end = s.ended_at ? ms(s.ended_at) : now;
          const left = ((start - t0) / total) * 100;
          const width = Math.max(((end - start) / total) * 100, 0.6);
          const dur = (end - start) / 1000;
          return (
            <li key={s.id}>
              <button
                onClick={() => onSelect(s)}
                className={cx(
                  "grid w-full grid-cols-[minmax(220px,38%)_1fr_72px_64px] items-center gap-3 rounded px-2 py-1 text-left text-sm hover:bg-paper",
                  selectedId === s.id && "bg-paper",
                )}
              >
                <span className="flex min-w-0 items-center gap-1.5" style={{ paddingLeft: depth * 14 }}>
                  <k.icon size={14} className={cx("shrink-0", s.status === "error" ? "text-fail" : "text-ink-3")} aria-label={k.label} />
                  <span className={cx("truncate", depth === 0 && "font-medium")}>{s.name}</span>
                  {s.attempt > 1 && <span className="shrink-0 text-xs text-fail">attempt {s.attempt}</span>}
                  {s.status === "interrupted" && <span className="shrink-0 text-xs text-ink-3">interrupted</span>}
                </span>
                <span className="relative h-3.5 rounded-sm bg-line/40">
                  <span
                    data-testid={`bar-${s.id}`}
                    className={cx(
                      "absolute top-0 h-full rounded-sm",
                      s.status === "error" ? "bg-fail" : s.status === "interrupted" ? "bg-idle opacity-60" : k.bar,
                      s.status === "running" && "animate-pulse",
                    )}
                    style={{ left: `${+left.toFixed(4)}%`, width: `${+width.toFixed(4)}%` }}
                  />
                </span>
                <span className="text-right text-xs text-ink-3">{duration(dur)}</span>
                <span className="text-right text-xs text-ink-3">{Number(s.cost_usd) > 0 ? cost(s.cost_usd) : ""}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
