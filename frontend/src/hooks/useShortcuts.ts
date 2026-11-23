import { useEffect, useRef } from "react";

const typing = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
};

/**
 * App-wide keyboard shortcuts.
 * - ⌘K / Ctrl+K toggles the command menu from anywhere, even while typing.
 * - "/" opens it, "?" shows the shortcut list, and "g" then a letter jumps to a page.
 * Single keys are ignored while the person is typing in a field.
 */
export function useShortcuts({
  onPalette,
  onHelp,
  go,
}: {
  onPalette: () => void;
  onHelp: () => void;
  go: Record<string, () => void>;
}) {
  const pendingG = useRef<number | null>(null);
  const latest = useRef({ onPalette, onHelp, go });
  useEffect(() => {
    latest.current = { onPalette, onHelp, go };
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { onPalette, onHelp, go } = latest.current;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onPalette();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target) || e.defaultPrevented) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      const k = e.key.toLowerCase();
      if (pendingG.current !== null) {
        window.clearTimeout(pendingG.current);
        pendingG.current = null;
        if (go[k]) {
          e.preventDefault();
          go[k]();
        }
        return;
      }
      if (k === "g") {
        pendingG.current = window.setTimeout(() => (pendingG.current = null), 1000);
      } else if (e.key === "/") {
        e.preventDefault();
        onPalette();
      } else if (e.key === "?") {
        e.preventDefault();
        onHelp();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
