export const usd = (n: number | string | null | undefined, digits = 0) =>
  n === null || n === undefined
    ? "—"
    : Number(n).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits, minimumFractionDigits: digits });

export const cost = (n: number | string | null | undefined) => {
  if (n === null || n === undefined) return "—";
  const v = Number(n);
  return v < 1 ? `$${v.toFixed(v < 0.01 ? 4 : 3)}` : usd(v, 2);
};

export const pct = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${Math.round(n * 100)}%`);

export const num = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n.toLocaleString("en-US"));

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(m / 60);
  return h < 48 ? `${h}h ${m % 60}m` : `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export const humanize = (s: string) => (s.charAt(0).toUpperCase() + s.slice(1)).replace(/_/g, " ");
