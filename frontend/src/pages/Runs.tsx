import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { RunRoute } from "@/components/runs/RouteBoard";
import { Button, cx, Empty, ErrorNote, Kbd, PageHeader, Skeleton, StatusDot } from "@/components/ui";
import { useNow } from "@/hooks/useNow";
import { ago, cost, duration } from "@/lib/format";
import { STATUS, statusOf, type RunStatus } from "@/lib/status";

const FILTERS: (RunStatus | "")[] = ["", "running", "waiting_approval", "completed", "escalated", "failed", "cancelled"];

function Elapsed({ run }: { run: S["RunOut"] }) {
  const live = run.status === "running" || run.status === "waiting_approval";
  const now = useNow(live ? 1000 : null);
  return <>{duration(run.duration_s ?? (now - new Date(run.started_at).getTime()) / 1000)}</>;
}

export default function Runs() {
  const { tenant } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as RunStatus | "";
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDeferredValue(text.trim());
  const [cursor, setCursor] = useState(-1);
  const searchBox = useRef<HTMLInputElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (q) next.set("q", q);
    else next.delete("q");
    if (next.toString() !== params.toString()) setParams(next, { replace: true });
  }, [q, params, setParams]);

  const counts = useQuery({
    queryKey: ["runs", "counts", tenant?.tenant_id, q],
    queryFn: () => api.get<Record<string, number>>("/api/runs/counts", { q }),
  });
  const list = useInfiniteQuery({
    queryKey: ["runs", "list", tenant?.tenant_id, status, q],
    queryFn: ({ pageParam }) => api.get<S["RunPage"]>("/api/runs", { status, q, limit: 40, before: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);

  // Load older runs as the end of the table scrolls into view.
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !list.hasNextPage) return;
    const io = new IntersectionObserver((es) => es[0]?.isIntersecting && !list.isFetchingNextPage && list.fetchNextPage(), { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [list.hasNextPage, list.isFetchingNextPage, list]);

  // J/K move through rows, Enter opens, F focuses the search box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      if (e.key === "j") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, items.length - 1));
      }
      else if (e.key === "k") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      }
      else if (e.key === "Enter" && items[cursor]) {
        e.preventDefault();
        navigate(`/runs/${items[cursor].id}`);
      }
      else if (e.key === "f") {
        e.preventDefault();
        searchBox.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, cursor, navigate]);
  useEffect(() => {
    document.querySelector(`[data-row="${cursor}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [cursor]);

  const setStatus = (s: string) => {
    const next = new URLSearchParams(params);
    if (s) next.set("status", s);
    else next.delete("status");
    setParams(next, { replace: true });
    setCursor(-1);
  };

  return (
    <>
      <PageHeader title="Runs" sub="Every workflow, conversation and approved action, newest first. Updates live." />

      <div className="mb-5 flex flex-col gap-4">
        <label className="relative block max-w-md">
          <span className="sr-only">Search runs</span>
          <Search size={16} className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            ref={searchBox}
            value={text}
            onChange={(e) => (setText(e.target.value), setCursor(-1))}
            onKeyDown={(e) => e.key === "Escape" && (setText(""), e.currentTarget.blur())}
            placeholder="Search by title or customer"
            className="h-10 w-full rounded-full bg-panel pr-16 pl-10 text-[15px] shadow-[var(--card-shadow)] outline-none transition-shadow placeholder:text-ink-3 focus:shadow-[0_0_0_3px_var(--accent-soft),0_0_0_1px_var(--accent)]"
          />
          {text ? (
            <button onClick={() => setText("")} className="absolute top-1/2 right-2 -translate-y-1/2 rounded-md p-1 text-ink-3 hover:bg-sunk" aria-label="Clear search">
              <X size={15} />
            </button>
          ) : (
            <Kbd className="absolute top-1/2 right-3 -translate-y-1/2">F</Kbd>
          )}
        </label>
        <div role="radiogroup" aria-label="Filter by status" className="-mx-1 flex flex-wrap gap-1.5">
          {FILTERS.map((s) => {
            const on = s === status;
            const n = counts.data?.[s || "all"];
            return (
              <button
                key={s || "all"}
                role="radio"
                aria-checked={on}
                onClick={() => setStatus(s)}
                className={cx(
                  "inline-flex h-8 items-center gap-2 rounded-full px-3.5 text-[13px] font-medium transition-[background-color,color,transform] duration-150 active:scale-[0.97]",
                  on ? "bg-accent text-white" : "bg-panel text-ink-2 shadow-[var(--card-shadow)] hover:text-ink",
                )}
              >
                {s && <span className={cx("h-1.5 w-1.5 rounded-full", on ? "bg-white" : statusOf(s).color)} aria-hidden />}
                {s ? STATUS[s].label : "All"}
                {n !== undefined && <span className={cx("tabular-nums", on ? "text-white/75" : "text-ink-3")}>{n.toLocaleString()}</span>}
              </button>
            );
          })}
        </div>
      </div>

      <ErrorNote error={list.error} />
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full table-fixed text-sm">
            <thead className="text-left text-[13px] text-ink-3">
              <tr>
                <th className="px-5 py-2.5 font-normal md:w-[40%]">Run</th>
                <th className="hidden w-[30%] px-5 py-2.5 font-normal md:table-cell">Route</th>
                <th className="hidden w-[11%] px-5 py-2.5 font-normal md:table-cell">Started</th>
                <th className="w-20 px-3 py-2.5 text-right font-normal md:w-[10%] md:px-5">Duration</th>
                <th className="w-20 py-2.5 pr-5 pl-3 text-right font-normal md:w-[9%] md:pl-5">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/70">
              {list.isLoading &&
                [0, 1, 2, 3, 4].map((i) => (
                  <tr key={i}>
                    <td colSpan={5} className="px-5 py-3">
                      <Skeleton className="h-6" />
                    </td>
                  </tr>
                ))}
              {items.map((r, i) => (
                <tr
                  key={r.id}
                  data-row={i}
                  onClick={() => navigate(`/runs/${r.id}`)}
                  className={cx("cursor-pointer transition-colors hover:bg-sunk/50 active:bg-sunk", i === cursor && "bg-accent-soft hover:bg-accent-soft")}
                >
                  <td className="max-w-0 px-5 py-3.5">
                    <span className="flex items-center gap-2.5">
                      <StatusDot status={r.status} />
                      <span className="min-w-0">
                        <Link to={`/runs/${r.id}`} onClick={(e) => e.stopPropagation()} className="block font-medium text-ink hover:text-accent md:truncate">
                          {r.title || "Untitled run"}
                        </Link>
                        <span className={cx("text-xs", statusOf(r.status).text)}>{statusOf(r.status).label}</span>
                      </span>
                    </span>
                  </td>
                  <td className="hidden max-w-0 px-5 py-3.5 md:table-cell">
                    <RunRoute run={r} compact />
                  </td>
                  <td className="hidden px-5 py-3.5 whitespace-nowrap text-ink-3 md:table-cell" title={new Date(r.started_at).toLocaleString()}>
                    {ago(r.started_at)}
                  </td>
                  <td className="px-3 py-3.5 text-right whitespace-nowrap md:px-5">
                    <Elapsed run={r} />
                  </td>
                  <td className="py-3.5 pr-5 pl-3 text-right whitespace-nowrap text-ink-2 md:pl-5">{Number(r.total_cost_usd) > 0 ? cost(r.total_cost_usd) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!list.isLoading && !items.length && (
          <Empty title={q ? `No runs match “${q}”` : "No runs with this status"} action={(q || status) && <Button onClick={() => (setText(""), setStatus(""))}>Clear filters</Button>}>
            Runs appear here as soon as an event starts a workflow.
          </Empty>
        )}
      </div>
      <div ref={sentinel} className="h-px" />
      {list.isFetchingNextPage && <Skeleton className="mt-3 h-10" />}
      {items.length > 0 && (
        <p className="mt-4 flex items-center gap-2 text-xs text-ink-3">
          <Kbd>J</Kbd>
          <Kbd>K</Kbd> to move, <Kbd>↵</Kbd> to open
        </p>
      )}
    </>
  );
}
