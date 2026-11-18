import { useEffect, useState } from "react";

/** Current time that re-renders every `ms` (or never, when ms is null). Keeps render pure. */
export function useNow(ms: number | null = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (ms === null) return;
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
