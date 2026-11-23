import { useCallback, useEffect, useState } from "react";

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

function apply(t: Theme) {
  const el = document.documentElement;
  if (t === "system") delete el.dataset.theme;
  else el.dataset.theme = t;
}

/** The person's theme choice. "system" follows the OS; the choice survives reloads (index.html applies it before paint). */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read);
  useEffect(() => apply(theme), [theme]);
  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try {
      if (t === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, t);
    } catch {
      /* private mode: the choice lasts for this page only */
    }
  }, []);
  return { theme, setTheme };
}
