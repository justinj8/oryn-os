import { X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";
import { statusOf } from "@/lib/status";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" };
export function Button({ variant = "secondary", className, ...p }: ButtonProps) {
  return (
    <button
      {...p}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-ink text-paper hover:bg-ink-2",
        variant === "secondary" && "border border-line bg-panel text-ink hover:border-ink-3",
        variant === "danger" && "border border-fail/40 bg-panel text-fail hover:bg-fail/10",
        variant === "ghost" && "text-ink-2 hover:bg-line/50",
        className,
      )}
    />
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-ink-3">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Section({ title, aside, children, className }: { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-line bg-panel", className)}>
      {title && (
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="font-display text-lg font-semibold">{title}</h2>
          {aside}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function StatusPill({ status }: { status: string }) {
  const s = statusOf(status);
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium">
      <span className={cx("h-2 w-2 rounded-full", s.color)} aria-hidden />
      {s.label}
    </span>
  );
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "hold" | "fail" | "clear" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-line/60 text-ink-2",
        tone === "hold" && "bg-hold/15 text-hold",
        tone === "fail" && "bg-fail/12 text-fail",
        tone === "clear" && "bg-clear/12 text-clear",
      )}
    >
      {children}
    </span>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="font-display text-lg font-semibold">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-ink-3">{children}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded bg-line/70", className)} />;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="rounded-md border border-fail/30 bg-fail/8 px-3 py-2 text-sm text-fail">{(error as Error).message}</p>;
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/30" onClick={onClose} role="presentation">
      <aside
        role="dialog"
        aria-label={title}
        className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-panel p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">{title}</h2>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            <X size={16} />
          </Button>
        </div>
        {children}
      </aside>
    </div>
  );
}

export function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-md bg-paper p-3 text-xs leading-relaxed text-ink-2">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
