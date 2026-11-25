import { cx } from "@/components/ui";

/** The Oryn mark: a ring (the workforce) with one signal on it (a run in flight). */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cx("shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#1d1d1f" />
      <circle cx="16" cy="16" r="8" fill="none" strokeWidth="2.6" stroke="#ffffff" />
      <circle cx="22.2" cy="10.8" r="3.4" strokeWidth="1.6" stroke="#1d1d1f" className="fill-accent" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <LogoMark className="h-7 w-7" />
      <span className="text-[17px] font-semibold tracking-[-0.02em] text-ink">Oryn OS</span>
    </span>
  );
}
