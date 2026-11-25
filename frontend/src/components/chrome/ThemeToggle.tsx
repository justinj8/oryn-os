import { Moon, Sun } from "lucide-react";
import { cx } from "@/components/ui";
import { useTheme } from "@/hooks/useTheme";

/** One tap between light and dark. The icon shows what you'll switch to. */
export function ThemeToggle({ className }: { className?: string }) {
  const { dark, toggle } = useTheme();
  const label = dark ? "Switch to light" : "Switch to dark";
  return (
    <button
      onClick={toggle}
      aria-label={label}
      title={label}
      className={cx("relative flex h-7 w-7 items-center justify-center overflow-hidden rounded-md text-ink-2 transition-colors hover:bg-fill hover:text-ink", className)}
    >
      <Sun size={15} strokeWidth={2} className={cx("absolute transition-all duration-300 ease-[var(--ease-spring)]", dark ? "scale-100 rotate-0 opacity-100" : "scale-50 -rotate-90 opacity-0")} aria-hidden />
      <Moon size={15} strokeWidth={2} className={cx("absolute transition-all duration-300 ease-[var(--ease-spring)]", dark ? "scale-50 rotate-90 opacity-0" : "scale-100 rotate-0 opacity-100")} aria-hidden />
    </button>
  );
}
