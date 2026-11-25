import { useCallback, useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";
const KEY = "oryn.theme";

function read(): Theme {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

/*
 * One theme for the whole page, shared by every control that shows or changes it (the sidebar's
 * Light/Dark/Auto, the toolbar's sun and moon). It also follows changes made in other open windows of
 * the site, such as the app embedded on the website, through the storage event.
 */
let current: Theme = typeof window === "undefined" ? "system" : read();
const listeners = new Set<() => void>();

function apply(t: Theme) {
  const el = document.documentElement;
  if (t === "system") delete el.dataset.theme;
  else el.dataset.theme = t;
}

function set(t: Theme) {
  current = t;
  apply(t);
  listeners.forEach((l) => l());
}

const mq = typeof window !== "undefined" ? window.matchMedia?.("(prefers-color-scheme: dark)") : undefined;

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  const onStorage = (e: StorageEvent) => e.key === KEY && set(read());
  window.addEventListener("storage", onStorage);
  mq?.addEventListener?.("change", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
    mq?.removeEventListener?.("change", onChange);
  };
}

/** The person's theme: "system" follows the OS. index.html applies the saved choice before first paint. */
export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => current, () => "system" as Theme);
  const osDark = useSyncExternalStore(subscribe, () => !!mq?.matches, () => false);
  const setTheme = useCallback((t: Theme) => {
    try {
      if (t === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, t);
    } catch {
      /* private mode: the choice lasts for this page only */
    }
    set(t);
  }, []);
  const dark = theme === "dark" || (theme === "system" && osDark);
  /** Flip between light and dark, from whatever is showing now. */
  const toggle = useCallback(() => setTheme(dark ? "light" : "dark"), [dark, setTheme]);
  return { theme, setTheme, dark, toggle };
}
