import { CircleAlert, CircleCheck } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; text: string; tone: "info" | "error" };
const Ctx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-2), { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-5 z-[60] flex flex-col items-center gap-2 px-4" role="status" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex max-w-md animate-[rise_220ms_var(--ease-out)] items-center gap-2.5 rounded-xl bg-ink py-2.5 pr-4 pl-3 text-sm text-paper shadow-[0_12px_32px_-8px_rgb(0_0_0/0.35)]"
          >
            {t.tone === "error" ? (
              <CircleAlert size={16} className="shrink-0 text-fail" aria-hidden />
            ) : (
              <CircleCheck size={16} className="shrink-0 text-clear" aria-hidden />
            )}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
