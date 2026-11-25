import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Copy, ExternalLink, PanelRightOpen, RotateCcw, Route, Search, X } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { RunInspector, TEMPORAL_UI, useRerun } from "@/components/runs/RunInspector";
import { cx, Empty, ErrorNote, Kbd, Skeleton, StatusDot, Toolbar } from "@/components/ui";
import { ContextMenu, type MenuState } from "@/components/ui/ContextMenu";
import { useToast } from "@/components/ui/toast";
import { useNow } from "@/hooks/useNow";
import { ago, cost, duration } from "@/lib/format";
import { STATUS, statusOf, type RunStatus } from "@/lib/status";

const FILTERS: (RunStatus | "")[] = ["", "running", "waiting_approval", "completed", "escalated", "failed", "cancelled"];
type Run = S["RunOut"];

function Elapsed({ run }: { run: Run }) {
  const live = run.status === "running" || run.status === "waiting_approval";
  const now = useNow(live ? 1000 : null);
  return <>{duration(run.duration_s ?? (now - new Date(run.started_at).getTime()) / 1000)}</>;
}

function RunRow({ run, selected, fresh, onOpen, onMenu }: { run: Run; selected: boolean; fresh: boolean; onOpen: () => void; onMenu: (e: React.MouseEvent) => void }) {
  const st = statusOf(run.status);
  const route = run.route.length ? run.route.join(" → ") : run.kind === "conversation" ? "Conversation" : "Starting";
  return (
    <li
      role="option"
      aria-selected={selected}
      data-run={run.id}
      onClick={onOpen}
      onContextMenu={onMenu}
      className={cx(
        "mx-2 cursor-default rounded-lg px-3 py-2.5 select-none",
        selected ? "bg-select text-white" : "hover:bg-fill",
        fresh && !selected && "animate-[rise_380ms_var(--ease-spring)] bg-accent-soft",
      )}
    >
      <div className="flex items-baseline gap-2">
        <StatusDot status={run.status} className={cx("translate-y-[-1px]", selected && "ring-2 ring-white/70")} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{run.title || "Untitled run"}</span>
        <span className={cx("shrink-0 text-[11.5px] tabular-nums", selected ? "text-white/80" : "text-ink-3")} title={new Date(run.started_at).toLocaleString()}>
          {ago(run.started_at)}
        </span>
      </div>
      <div className={cx("mt-0.5 flex items-baseline gap-2 pl-4 text-[12px]", selected ? "text-white/85" : "text-ink-3")}>
        <span className="min-w-0 flex-1 truncate">{route}</span>
        <span className={cx("shrink-0", !selected && st.text)}>{st.label}</span>
      </div>
      <div className={cx("mt-0.5 flex gap-3 pl-4 text-[11.5px] tabular-nums", selected ? "text-white/75" : "text-ink-3")}>
        <span>
          <Elapsed run={run} />
        </span>
        {Number(run.total_cost_usd) > 0 && <span>{cost(run.total_cost_usd)}</span>}
      </div>
    </li>
  );
}

export default function Runs() {
  const { tenant, can } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const { runId } = useParams();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as RunStatus | "";
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDeferredValue(text.trim());
  const [menu, setMenu] = useState<MenuState>(null);
  const [menuRun, setMenuRun] = useState<Run | null>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const rerun = useRerun(menuRun?.id ?? "");

  useEffect(() => {
    document.title = "Runs · Oryn OS";
  }, []);
  useEffect(() => {
    const next = new URLSearchParams(params);
    if (q) next.set("q", q);
    else next.delete("q");
    if (next.toString() !== params.toString()) setParams(next, { replace: true });
  }, [q, params, setParams]);

  const counts = useQuery({ queryKey: ["runs", "counts", tenant?.tenant_id, q], queryFn: () => api.get<Record<string, number>>("/api/runs/counts", { q }) });
  const runs = useInfiniteQuery({
    queryKey: ["runs", "list", tenant?.tenant_id, status, q],
    queryFn: ({ pageParam }) => api.get<S["RunPage"]>("/api/runs", { status, q, limit: 40, before: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = useMemo(() => runs.data?.pages.flatMap((p) => p.items) ?? [], [runs.data]);

  // Rows that arrive after the first load slide in and glow briefly, so live work is noticed without a banner.
  const [seen, setSeen] = useState<Set<string> | null>(null);
  const fresh = useMemo(() => new Set(seen ? items.filter((r) => !seen.has(r.id)).map((r) => r.id) : []), [items, seen]);
  const primed = seen !== null;
  useEffect(() => {
    if (!runs.isSuccess) return;
    const t = setTimeout(() => setSeen(new Set(items.map((r) => r.id))), primed ? 1600 : 0);
    return () => clearTimeout(t);
  }, [items, runs.isSuccess, primed]);

  const index = items.findIndex((r) => r.id === runId);
  const open = (r: Run) => navigate({ pathname: `/runs/${r.id}`, search: params.toString() }, { replace: !!runId });

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !runs.hasNextPage) return;
    const io = new IntersectionObserver((es) => es[0]?.isIntersecting && !runs.isFetchingNextPage && runs.fetchNextPage(), { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, [runs.hasNextPage, runs.isFetchingNextPage, runs]);

  // J/K (or arrows) move the selection and the inspector follows; F focuses search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (document.querySelector('[aria-modal="true"], [role="menu"]')) return;
      const move = (d: number) => {
        e.preventDefault();
        const next = items[Math.min(Math.max(index + d, 0), items.length - 1)];
        if (next) open(next);
      };
      if (e.key === "j" || e.key === "ArrowDown") move(index < 0 ? 0 : 1);
      else if (e.key === "k" || e.key === "ArrowUp") move(-1);
      else if (e.key === "f") {
        e.preventDefault();
        searchBox.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  useEffect(() => {
    if (runId) list.current?.querySelector(`[data-run="${runId}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [runId]);

  const setStatus = (s: string) => {
    const next = new URLSearchParams(params);
    if (s) next.set("status", s);
    else next.delete("status");
    setParams(next, { replace: true });
  };

  const showMenu = (e: React.MouseEvent, r: Run) => {
    e.preventDefault();
    setMenuRun(r);
    const finished = r.status !== "running" && r.status !== "waiting_approval";
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: "Open", icon: PanelRightOpen, onSelect: () => open(r) },
        { label: "Run again", icon: RotateCcw, disabled: !(finished && r.rerunnable && can("operator")), onSelect: () => rerun.mutate() },
        "separator",
        {
          label: "Copy link",
          icon: Copy,
          onSelect: () => {
            navigator.clipboard?.writeText(`${window.location.origin}/runs/${r.id}`);
            toast("Link copied");
          },
        },
        { label: "Open in Temporal", icon: ExternalLink, onSelect: () => window.open(`${TEMPORAL_UI}/namespaces/default/workflows/${encodeURIComponent(r.temporal_workflow_id)}`, "_blank") },
      ],
    });
  };

  const total = counts.data?.[status || "all"];
  return (
    <>
      <section
        aria-label="Run list"
        className={cx("flex min-h-0 w-full shrink-0 flex-col border-r border-line/80 lg:w-[380px] xl:w-[420px]", runId && "hidden lg:flex")}
      >
        <Toolbar title="Runs" local>
          {total !== undefined && <span className="text-[12px] text-ink-3 tabular-nums">{total.toLocaleString()}</span>}
        </Toolbar>
        <div className="space-y-2.5 border-b border-line/70 px-3 py-3">
          <label className="relative block">
            <span className="sr-only">Search runs</span>
            <Search size={13} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-3" aria-hidden />
            <input
              ref={searchBox}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setText("");
                  e.currentTarget.blur();
                }
              }}
              placeholder="Search by title or customer"
              className="h-7 w-full rounded-md bg-fill pr-8 pl-7 text-[13px] outline-none placeholder:text-ink-3 focus:bg-panel focus:shadow-[0_0_0_3px_var(--accent-soft),0_0_0_1px_var(--accent)]"
            />
            {text ? (
              <button onClick={() => setText("")} className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-0.5 text-ink-3 hover:text-ink" aria-label="Clear search">
                <X size={13} />
              </button>
            ) : (
              <Kbd className="absolute top-1/2 right-1.5 h-4 min-w-4 -translate-y-1/2 text-[10px]">F</Kbd>
            )}
          </label>
          <div role="radiogroup" aria-label="Filter by status" className="-mx-0.5 flex gap-1 overflow-x-auto pb-0.5">
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
                    "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[11.5px] font-medium transition-colors",
                    on ? "bg-ink text-panel" : "bg-fill text-ink-2 hover:bg-fill-2",
                  )}
                >
                  {s && <span className={cx("h-1.5 w-1.5 rounded-full", statusOf(s).color)} aria-hidden />}
                  {s ? STATUS[s].label : "All"}
                  {n !== undefined && n > 0 && <span className={cx("tabular-nums", on ? "opacity-70" : "text-ink-3")}>{n}</span>}
                </button>
              );
            })}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto py-1.5">
          <ErrorNote error={runs.error} />
          {runs.isLoading ? (
            <div className="space-y-2 px-3">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-[66px]" />
              ))}
            </div>
          ) : items.length ? (
            <ul ref={list} role="listbox" aria-label="Runs" className="space-y-px">
              {items.map((r) => (
                <RunRow key={r.id} run={r} selected={r.id === runId} fresh={fresh.has(r.id)} onOpen={() => open(r)} onMenu={(e) => showMenu(e, r)} />
              ))}
            </ul>
          ) : (
            <Empty title={q ? `No runs match “${q}”` : "No runs with this status"}>Runs appear here the moment an event starts a workflow.</Empty>
          )}
          <div ref={sentinel} className="h-px" />
          {runs.isFetchingNextPage && <Skeleton className="mx-3 mt-2 h-14" />}
        </div>
      </section>

      {runId ? (
        <RunInspector key={runId} runId={runId} onBack={() => navigate({ pathname: "/runs", search: params.toString() })} />
      ) : (
        <div className="hidden min-w-0 flex-1 flex-col lg:flex">
          <Toolbar />
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-fill text-ink-3">
              <Route size={26} strokeWidth={1.6} />
            </span>
            <p className="text-[15px] font-semibold">Select a run</p>
            <p className="max-w-[28ch] text-[13px] text-ink-3">
              See its route, trace, approvals and what the agents shared. Use <Kbd>J</Kbd> <Kbd>K</Kbd> to move through the list.
            </p>
          </div>
        </div>
      )}
      <ContextMenu menu={menu} onClose={() => setMenu(null)} />
    </>
  );
}
