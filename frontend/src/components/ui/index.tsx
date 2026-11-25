import { X } from "lucide-react";
import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { statusOf } from "@/lib/status";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "accent";
  size?: "sm" | "md" | "lg";
};
/** Filled, pill-shaped buttons. Primary carries the accent; secondary is a quiet gray fill. */
export function Button({ variant = "secondary", size = "md", className, ...p }: ButtonProps) {
  return (
    <button
      {...p}
      className={cx(
        "inline-flex select-none items-center justify-center gap-1.5 rounded-full font-medium whitespace-nowrap transition-[background-color,color,transform,opacity] duration-150 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-40",
        size === "sm" && "h-7 px-3 text-[12.5px]",
        size === "md" && "h-8 px-3.5 text-[13px]",
        size === "lg" && "h-10 px-5 text-[14px]",
        (variant === "primary" || variant === "accent") && "bg-accent text-white hover:brightness-110",
        variant === "secondary" && "bg-sunk text-ink hover:bg-line",
        variant === "danger" && "bg-fail/10 text-fail hover:bg-fail/15",
        variant === "ghost" && "text-accent hover:bg-accent/8",
        className,
      )}
    />
  );
}

/* Layout hands every toolbar the app-wide controls (search, status, activity) through this context. */
type Chrome = { toolbar: ReactNode };
export const ChromeContext = createContext<Chrome | null>(null);

/** A window toolbar: the title on the left, this view's controls and the app-wide ones on the right. */
/** ``local`` toolbars (a list pane beside an inspector) leave the app-wide controls to the pane on the right. */
export function Toolbar({ title, children, leading, className, local }: { title?: ReactNode; children?: ReactNode; leading?: ReactNode; className?: string; local?: boolean }) {
  const chrome = useContext(ChromeContext);
  return (
    <div className={cx("sticky top-0 z-20 flex h-[52px] shrink-0 items-center gap-2 border-b border-line/70 bg-pane pr-3 pl-12 backdrop-blur-xl backdrop-saturate-150 md:px-5", className)}>
      {leading}
      {title && <h1 className="min-w-0 truncate text-[15px] font-semibold tracking-[-0.012em]">{title}</h1>}
      <div className="ml-auto flex items-center gap-1.5">
        {children}
        {chrome?.toolbar && <span className={cx("flex items-center gap-1.5", local && "lg:hidden")}>{chrome.toolbar}</span>}
      </div>
    </div>
  );
}

/** A scrolling page: toolbar on top, an optional one-line description, then content. */
export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · Oryn OS`;
  }, [title]);
  return (
    <div className="-mx-5 mb-6 md:-mx-8">
      <Toolbar title={title}>{actions}</Toolbar>
      {sub && <div className="px-5 pt-5 text-[13px] text-ink-3 md:px-8">{sub}</div>}
    </div>
  );
}

export function Section({
  title,
  aside,
  children,
  className,
  flush,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={cx("card", className)}>
      {title && (
        <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-1">
          <h2 className="text-[14px] font-semibold tracking-[-0.01em]">{title}</h2>
          {aside && <div className="text-[13px] text-ink-3">{aside}</div>}
        </div>
      )}
      <div className={flush ? "" : "p-5 pt-3"}>{children}</div>
    </section>
  );
}

export function StatusDot({ status, className }: { status: string; className?: string }) {
  const s = statusOf(status);
  const live = status === "running";
  return <span className={cx("inline-block h-2 w-2 shrink-0 rounded-full", s.color, live && "beacon", className)} aria-hidden />;
}

export function StatusPill({ status }: { status: string }) {
  const s = statusOf(status);
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium">
      <StatusDot status={status} />
      <span className={s.text}>{s.label}</span>
    </span>
  );
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "hold" | "fail" | "clear" | "accent" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-px text-xs font-medium",
        tone === "neutral" && "bg-sunk text-ink-2",
        tone === "hold" && "bg-hold/12 text-hold",
        tone === "fail" && "bg-fail/10 text-fail",
        tone === "clear" && "bg-clear/12 text-clear",
        tone === "accent" && "bg-accent-soft text-accent",
      )}
    >
      {children}
    </span>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd className={cx("inline-flex h-5 min-w-5 items-center justify-center rounded-md bg-sunk px-1 font-sans text-[11px] font-medium text-ink-3", className)}>
      {children}
    </kbd>
  );
}

/** A segmented control whose white thumb slides to the chosen option. Arrow keys move the choice. */
export function Segmented<T extends string | number>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  label: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [thumb, setThumb] = useState<{ x: number; w: number } | null>(null);
  const index = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const labels = options.map((o) => String(o.label)).join("|");
  useLayoutEffect(() => {
    const el = refs.current[index];
    // Measure the chosen option so the thumb follows the real layout.
    if (el) setThumb({ x: el.offsetLeft, w: el.offsetWidth });
  }, [index, labels]);
  const move = (i: number) => {
    const n = (i + options.length) % options.length;
    onChange(options[n].value);
    refs.current[n]?.focus();
  };
  return (
    <div role="radiogroup" aria-label={label} className="relative inline-flex rounded-[10px] bg-sunk p-0.5">
      {thumb && (
        <span
          aria-hidden
          className="absolute top-0.5 bottom-0.5 left-0 rounded-[8px] bg-panel shadow-[0_0_0_0.5px_rgb(0_0_0/0.04),0_2px_6px_rgb(0_0_0/0.10)] transition-[transform,width] duration-300 ease-[var(--ease-spring)]"
          style={{ width: thumb.w, transform: `translateX(${thumb.x}px)` }}
        />
      )}
      {options.map((o, i) => {
        const on = i === index;
        return (
          <button
            key={String(o.value)}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                e.preventDefault();
                move(i + 1);
              }
              if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                e.preventDefault();
                move(i - 1);
              }
            }}
            className={cx(
              "relative z-10 h-7 rounded-[8px] px-3.5 text-[13px] font-medium transition-colors",
              on ? "text-ink" : "text-ink-3 hover:text-ink",
              !thumb && on && "bg-panel",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** A change against the previous period. ``good`` colors it: true green, false red, null neutral. */
export type Delta = { text: string; good: boolean | null };

export function Figure({
  label,
  value,
  note,
  testId,
  size = "md",
  delta,
}: {
  label: ReactNode;
  value: ReactNode;
  note?: ReactNode;
  testId?: string;
  size?: "md" | "lg";
  delta?: Delta | null;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] text-ink-3">{label}</dt>
      <dd className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className={cx("font-figure text-ink", size === "lg" ? "text-[34px]" : "text-[24px]")} data-testid={testId}>
          {value}
        </span>
        {note && <span className="text-[13px] text-ink-3">{note}</span>}
      </dd>
      {delta && <DeltaText delta={delta} className="mt-1.5" />}
    </div>
  );
}

export function DeltaText({ delta, className }: { delta: Delta; className?: string }) {
  return (
    <p className={cx("text-[13px] font-medium", delta.good === null ? "text-ink-3" : delta.good ? "text-clear" : "text-fail", className)}>
      {delta.text}
    </p>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="px-6 py-14 text-center">
      <p className="text-[17px] font-semibold tracking-[-0.022em]">{title}</p>
      {children && <div className="mx-auto mt-1.5 max-w-md text-[15px] text-ink-3">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cx("relative overflow-hidden rounded-2xl bg-sunk", className)} aria-hidden>
      <div className="absolute inset-0 animate-[sweep_1.4s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-panel/60 to-transparent" />
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-2xl bg-fail/8 px-4 py-3 text-sm text-fail">
      {(error as Error).message}
    </p>
  );
}

/** A sheet that slides in from the edge with a spring, over a dimmed window. Escape or a click outside closes it. */
export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!open) return;
    const back = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => {
      window.removeEventListener("keydown", k);
      back?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex animate-[fade_200ms_ease-out] justify-end bg-black/25" onClick={onClose} role="presentation">
      <aside
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="m-2 flex h-[calc(100%-16px)] w-full max-w-xl animate-[slide-in_380ms_var(--ease-spring)] flex-col overflow-hidden rounded-[22px] bg-panel shadow-[var(--pop-shadow)] outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
          <h2 className="truncate text-[17px] font-semibold tracking-[-0.022em]">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="flex h-7 w-7 items-center justify-center rounded-full bg-sunk text-ink-3 hover:text-ink">
            <X size={14} strokeWidth={2.5} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 pb-5">{children}</div>
      </aside>
    </div>
  );
}

export function Json({ value }: { value: unknown }) {
  return <pre className="max-h-80 overflow-auto rounded-2xl bg-sunk p-4 font-mono text-xs leading-relaxed text-ink-2">{JSON.stringify(value, null, 2)}</pre>;
}

export function Avatar({ name, className }: { name: string; className?: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  return (
    <span
      aria-hidden
      className={cx(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-[#a1a1a6] to-[#7c7c80] text-[12px] font-semibold text-white",
        className,
      )}
    >
      {initials || "?"}
    </span>
  );
}

/** An iOS-style on/off switch that says what it toggles. role="switch" so screen readers announce on and off. */
export function Switch({
  checked,
  onChange,
  label,
  disabled,
  showLabel,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
  showLabel?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={showLabel ? undefined : label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="group inline-flex items-center gap-3 text-[15px] disabled:cursor-not-allowed disabled:opacity-40"
    >
      <span className={cx("relative inline-flex h-[26px] w-[44px] shrink-0 items-center rounded-full transition-colors duration-200", checked ? "bg-switch" : "bg-line-2")}>
        <span
          className={cx(
            "absolute left-[2px] h-[22px] w-[22px] rounded-full bg-white shadow-[0_2px_4px_rgb(0_0_0/0.15),0_0_0_0.5px_rgb(0_0_0/0.04)] transition-transform duration-300 ease-[var(--ease-spring)]",
            checked && "translate-x-[18px]",
          )}
        />
      </span>
      {showLabel && <span>{label}</span>}
    </button>
  );
}
