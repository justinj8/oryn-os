import type { LucideIcon } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { cx } from "./index";

export type MenuItem = { label: string; icon?: LucideIcon; onSelect: () => void; disabled?: boolean; danger?: boolean } | "separator";
export type MenuState = { x: number; y: number; items: MenuItem[] } | null;

/** A right-click menu like macOS: opens at the pointer, stays on screen, closes on Escape, scroll or click. */
export function ContextMenu({ menu, onClose }: { menu: MenuState; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [active, setActive] = useState(-1);

  useLayoutEffect(() => {
    if (!menu || !box.current) return;
    const { width, height } = box.current.getBoundingClientRect();
    // Keep the menu inside the window, flipping it to the other side of the pointer if needed.
    setPos({
      x: Math.min(menu.x, window.innerWidth - width - 8),
      y: menu.y + height > window.innerHeight - 8 ? Math.max(8, menu.y - height) : menu.y,
    });
    setActive(-1);
    box.current.focus();
  }, [menu]);

  useEffect(() => {
    if (!menu) return;
    const close = () => onClose();
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("blur", close);
    };
  }, [menu, onClose]);

  if (!menu) return null;
  const actionable = menu.items.map((it, i) => (it !== "separator" && !it.disabled ? i : -1)).filter((i) => i >= 0);
  const step = (dir: 1 | -1) => {
    const at = actionable.indexOf(active);
    setActive(actionable[(at + dir + actionable.length) % actionable.length] ?? -1);
  };
  return (
    <div className="fixed inset-0 z-50" onMouseDown={onClose} onContextMenu={(e) => (e.preventDefault(), onClose())} role="presentation">
      <div
        ref={box}
        role="menu"
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
          else if (e.key === "ArrowDown") {
            e.preventDefault();
            step(1);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            step(-1);
          } else if (e.key === "Enter" && active >= 0) {
            const it = menu.items[active];
            if (it !== "separator") {
              onClose();
              it.onSelect();
            }
          }
        }}
        style={{ left: pos?.x ?? menu.x, top: pos?.y ?? menu.y, visibility: pos ? "visible" : "hidden" }}
        className="material absolute min-w-[200px] animate-[pop_140ms_var(--ease-out)] rounded-lg p-1 shadow-[var(--pop-shadow)] outline-none"
      >
        {menu.items.map((it, i) =>
          it === "separator" ? (
            <div key={i} className="mx-2 my-1 h-px bg-line" role="separator" />
          ) : (
            <button
              key={it.label}
              role="menuitem"
              disabled={it.disabled}
              onMouseEnter={() => setActive(i)}
              onClick={() => {
                onClose();
                it.onSelect();
              }}
              className={cx(
                "flex w-full items-center gap-2 rounded-[5px] px-2 py-1 text-left text-[13px] disabled:opacity-40",
                active === i ? "bg-select text-white" : it.danger ? "text-fail" : "text-ink",
              )}
            >
              {it.icon && <it.icon size={14} aria-hidden className={active === i ? "text-white" : "text-ink-3"} />}
              {it.label}
            </button>
          ),
        )}
      </div>
    </div>
  );
}
