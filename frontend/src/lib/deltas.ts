import type { Delta } from "@/components/ui";

/** Which way is good for a metric: up (more is better), down (less is better), or neither. */
export type Better = "up" | "down" | "none";

const arrow = (d: number) => (d > 0 ? "↑" : d < 0 ? "↓" : "");

function judge(change: number, better: Better): boolean | null {
  if (better === "none" || change === 0) return null;
  return better === "up" ? change > 0 : change < 0;
}

/**
 * Relative change between two amounts, e.g. "↑ 12% vs previous 30 days".
 * Returns null when there is nothing honest to say (no previous period, or it was zero).
 */
export function changeOf(cur: number | null | undefined, prev: number | null | undefined, range: number, better: Better = "up"): Delta | null {
  if (cur === null || cur === undefined || prev === null || prev === undefined) return null;
  if (prev === 0) return cur === 0 ? { text: `No change vs previous ${range} days`, good: null } : { text: "New this period", good: judge(cur, better) };
  const change = (cur - prev) / Math.abs(prev);
  const pct = Math.round(change * 100);
  if (pct === 0) return { text: `No change vs previous ${range} days`, good: null };
  return { text: `${arrow(pct)} ${Math.abs(pct)}% vs previous ${range} days`, good: judge(pct, better) };
}

/** Change between two rates in percentage points, e.g. "↑ 3 pts vs previous 30 days". */
export function pointsOf(cur: number | null | undefined, prev: number | null | undefined, range: number, better: Better = "up"): Delta | null {
  if (cur === null || cur === undefined || prev === null || prev === undefined) return null;
  const pts = Math.round((cur - prev) * 100);
  if (pts === 0) return { text: `No change vs previous ${range} days`, good: null };
  return { text: `${arrow(pts)} ${Math.abs(pts)} pts vs previous ${range} days`, good: judge(pts, better) };
}
