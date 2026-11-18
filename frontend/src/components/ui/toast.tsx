import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; text: string; tone: "info" | "error" };
const Ctx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="fixed right-4 bottom-4 z-50 flex flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={`rounded-md border px-4 py-2.5 text-sm shadow-lg ${t.tone === "error" ? "border-fail/40 bg-panel text-fail" : "border-line bg-ink text-paper"}`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
