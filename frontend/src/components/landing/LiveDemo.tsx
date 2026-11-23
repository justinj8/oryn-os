import { Check, Hand, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cx } from "@/components/ui";

/**
 * A client-side replay of the product's golden path, for visitors who are not signed in.
 * A lead arrives, Sales qualifies it and asks for a discount, and the visitor makes the call.
 * Nothing here talks to the API; the real thing is one click away in the demo workspace.
 */
type Phase = "arrive" | "qualify" | "hold" | "apply" | "book" | "done";
type Line = { at: number; text: string; tone?: "hold" | "clear" | "muted" };
const FIRST = "lead.created: Dana Reyes, heat pump install, $8,200 budget";

const STOPS = [
  { id: "lead", label: "Lead" },
  { id: "sales", label: "Sales" },
  { id: "approval", label: "You" },
  { id: "scheduler", label: "Scheduler" },
  { id: "booked", label: "Booked" },
] as const;

const REACHED: Record<Phase, number> = { arrive: 0, qualify: 1, hold: 2, apply: 2, book: 3, done: 4 };

export function LiveDemo() {
  const [phase, setPhase] = useState<Phase>("arrive");
  const [approved, setApproved] = useState<boolean | null>(null);
  const [lines, setLines] = useState<Line[]>([{ at: 0, text: FIRST }]);
  const t0 = useRef(0);
  const timers = useRef<number[]>([]);

  const log = (text: string, tone?: Line["tone"]) => setLines((ls) => [...ls, { at: (performance.now() - t0.current) / 1000, text, tone }]);
  const later = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));

  // Timer callbacks set state later, never during render or synchronously inside an effect.
  const schedule = () => {
    later(900, () => {
      setPhase("qualify");
      log("Sales looked up the contact and created a deal");
    });
    later(2300, () => {
      log("Sales proposed a 15% discount, above the 10% policy", "hold");
      setPhase("hold");
    });
  };

  const start = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    t0.current = performance.now();
    setApproved(null);
    setLines([{ at: 0, text: FIRST }]);
    setPhase("arrive");
    schedule();
  };

  useEffect(() => {
    t0.current = performance.now();
    schedule();
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const decide = (ok: boolean) => {
    setApproved(ok);
    setPhase("apply");
    log(ok ? "You approved the discount" : "You rejected the discount", ok ? "clear" : "muted");
    later(700, () => {
      log(ok ? "Discount applied, Sales handed off to Scheduler" : "Sales continued at list price and handed off");
      setPhase("book");
    });
    later(2100, () => {
      log("Scheduler booked Thu 10:00 and emailed a confirmation", "clear");
      setPhase("done");
    });
  };

  const reached = REACHED[phase];
  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-panel shadow-[0_40px_100px_-40px_rgb(0_0_0/0.35)]">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className={cx("h-2 w-2 rounded-full", phase === "done" ? "bg-clear" : phase === "hold" ? "bg-hold" : "bg-accent beacon")} aria-hidden />
          <span className="text-sm font-medium">New lead workflow for Dana Reyes</span>
        </div>
        <button onClick={start} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-ink-3 hover:bg-sunk hover:text-ink">
          <RotateCcw size={13} aria-hidden /> Replay
        </button>
      </div>

      <div className="px-5 pt-7 pb-6 sm:px-8">
        <ol className="flex items-center" aria-label="Run route">
          {STOPS.map((s, i) => {
            const done = i < reached || (i === reached && phase === "done");
            const here = i === reached && phase !== "done";
            const isHold = s.id === "approval" && (phase === "hold" || phase === "apply");
            return (
              <li key={s.id} className={cx("flex items-center", i < STOPS.length - 1 && "flex-1")}>
                <span className="flex flex-col items-center gap-2">
                  <span
                    className={cx(
                      "flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors duration-300",
                      isHold ? "border-hold bg-hold text-white" : done ? "border-ink bg-ink text-paper" : here ? "border-accent bg-accent text-white beacon" : "border-line-2 bg-panel text-ink-3",
                    )}
                  >
                    {isHold ? <Hand size={14} aria-hidden /> : done ? <Check size={14} strokeWidth={3} aria-hidden /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                  </span>
                  <span className={cx("text-xs", here || isHold ? "font-medium text-ink" : "text-ink-3")}>{s.label}</span>
                </span>
                {i < STOPS.length - 1 && (
                  <span className="relative mx-1 mb-6 h-0.5 flex-1 overflow-hidden rounded-full bg-line" aria-hidden>
                    <span
                      className={cx("absolute inset-y-0 left-0 rounded-full bg-ink transition-[width] duration-700 ease-out", i < reached ? "w-full" : "w-0")}
                    />
                    {i === reached && phase !== "hold" && phase !== "done" && (
                      <span className="absolute top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-accent [animation:signal_1.1s_var(--ease-out)_infinite]" />
                    )}
                  </span>
                )}
              </li>
            );
          })}
        </ol>

        <div className="mt-6 min-h-[132px]">
          {phase === "hold" ? (
            <div className="animate-[rise_220ms_var(--ease-out)] rounded-2xl border border-hold/30 bg-hold/[0.06] p-4">
              <p className="text-[13px] text-hold">Waiting on a person</p>
              <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="font-medium">Apply a 15% discount to Reyes Co</p>
                  <p className="text-sm text-ink-3">Above the 10% policy, so a person has to decide.</p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => decide(false)}
                    className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-2 bg-panel px-3.5 text-sm font-medium text-fail transition-colors hover:border-fail/50"
                  >
                    <X size={15} aria-hidden /> Reject
                  </button>
                  <button
                    onClick={() => decide(true)}
                    className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-3.5 text-sm font-medium text-paper transition-transform hover:bg-ink/85 active:scale-[0.98]"
                  >
                    <Check size={15} aria-hidden /> Approve
                  </button>
                </div>
              </div>
            </div>
          ) : phase === "done" ? (
            <div className="flex animate-[rise_220ms_var(--ease-out)] flex-wrap items-end justify-between gap-4 rounded-2xl bg-sunk p-4">
              <div>
                <p className="text-[13px] text-ink-3">{approved ? "Meeting booked, discount applied" : "Meeting booked at list price"}</p>
                <p className="font-figure text-[40px]">{approved ? "$6,970" : "$8,200"}</p>
              </div>
              <p className="max-w-[16rem] text-right text-sm text-ink-3">Every step, retry and decision is on the run's trace in the real dashboard.</p>
            </div>
          ) : (
            <ul className="space-y-1.5 font-mono text-[12.5px]" aria-live="polite">
              {lines.slice(-5).map((l, i) => (
                <li key={i} className={cx("flex gap-3", l.tone === "hold" ? "text-hold" : l.tone === "clear" ? "text-clear" : l.tone === "muted" ? "text-ink-3" : "text-ink-2")}>
                  <span className="w-10 shrink-0 text-right text-ink-3 tabular-nums">{l.at.toFixed(1)}s</span>
                  <span>{l.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
