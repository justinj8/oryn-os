import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Building2,
  CheckCircle2,
  CornerDownLeft,
  FlaskConical,
  Gauge,
  LogOut,
  Monitor,
  Moon,
  Plug,
  Plus,
  Route,
  Search,
  Settings,
  Sun,
  Workflow,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useDeferredValue, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { cx, Kbd } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import type { Theme } from "@/hooks/useTheme";
import { PRESETS } from "@/lib/presets";

export type Command = {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  keywords?: string;
  keys?: string[];
  run: () => void;
};

const HIT_ICON: Record<string, LucideIcon> = { approval: CheckCircle2, run: Route, agent: Bot, workflow: Workflow };
const HIT_GROUP: Record<string, string> = { approval: "Waiting on you", run: "Runs", agent: "Agents", workflow: "Workflows" };

/** Every word the person typed must appear; earlier and prefix matches rank higher. */
export function rank(query: string, c: Pick<Command, "label" | "keywords" | "group">): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const hay = `${c.label} ${c.keywords ?? ""} ${c.group}`.toLowerCase();
  const words = q.split(/\s+/);
  if (!words.every((w) => hay.includes(w))) return 0;
  const label = c.label.toLowerCase();
  if (label.startsWith(q)) return 4;
  if (label.split(/\s+/).some((w) => w.startsWith(words[0]))) return 3;
  return label.includes(words[0]) ? 2 : 1;
}

/** Mounted only while open, so every opening starts from an empty query. */
export function CommandPalette({
  onClose,
  theme,
  setTheme,
}: {
  onClose: () => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
}) {
  const nav = useNavigate();
  const { memberships, tenant, setTenant, logout, can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const deferred = useDeferredValue(query.trim());
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    input.current?.focus();
  }, []);

  const fire = useMutation({
    mutationFn: (p: (typeof PRESETS)[number]) => api.post<S["IngestOut"]>("/api/simulate/events", { type: p.type, payload: p.payload() }),
    onSuccess: (r) => {
      toast(r.run_ids.length ? `Started ${r.run_ids.length} run${r.run_ids.length > 1 ? "s" : ""}` : "Event received, but no workflow listens for it");
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const hits = useQuery({
    queryKey: ["search", tenant?.tenant_id, deferred],
    queryFn: () => api.get<S["SearchHit"][]>("/api/search", { q: deferred, limit: 4 }),
    enabled: deferred.length >= 2,
    staleTime: 5_000,
  });

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => nav(to);
    const base: Command[] = [
      { id: "go-overview", group: "Go to", label: "Overview", icon: Gauge, keys: ["G", "O"], run: go("/") },
      { id: "go-runs", group: "Go to", label: "Runs", icon: Route, keys: ["G", "R"], run: go("/runs") },
      { id: "go-approvals", group: "Go to", label: "Approvals", icon: CheckCircle2, keys: ["G", "A"], keywords: "inbox decide", run: go("/approvals") },
      { id: "go-agents", group: "Go to", label: "Agents", icon: Bot, keys: ["G", "E"], run: go("/agents") },
      { id: "go-workflows", group: "Go to", label: "Workflows", icon: Workflow, keys: ["G", "W"], run: go("/workflows") },
      { id: "go-connectors", group: "Go to", label: "Connectors", icon: Plug, keys: ["G", "C"], keywords: "integrations crm email phone", run: go("/connectors") },
      { id: "go-sim", group: "Go to", label: "Simulators", icon: FlaskConical, keys: ["G", "S"], keywords: "test chat phone email", run: go("/simulators") },
      { id: "go-settings", group: "Go to", label: "Settings", icon: Settings, keywords: "people api keys policy", run: go("/settings") },
    ];
    if (can("admin")) {
      base.push({ id: "new-workflow", group: "Create", label: "New workflow", hint: "Describe it in plain English", icon: Plus, keywords: "builder automate", run: go("/workflows/new") });
    }
    if (can("operator")) {
      for (const p of PRESETS) {
        base.push({ id: `sim-${p.id}`, group: "Simulate", label: p.label, hint: p.hint, icon: Zap, keywords: `fire send event ${p.type}`, run: () => fire.mutate(p) });
      }
    }
    for (const m of memberships) {
      if (m.tenant_id === tenant?.tenant_id) continue;
      base.push({ id: `ws-${m.tenant_id}`, group: "Workspace", label: `Switch to ${m.name}`, icon: Building2, keywords: "tenant business", run: () => (setTenant(m.tenant_id), qc.clear(), nav("/")) });
    }
    const themes: [Theme, string, LucideIcon][] = [
      ["light", "Use light theme", Sun],
      ["dark", "Use dark theme", Moon],
      ["system", "Match system theme", Monitor],
    ];
    for (const [t, label, icon] of themes) {
      if (t !== theme) base.push({ id: `theme-${t}`, group: "Preferences", label, icon, keywords: "appearance mode", run: () => setTheme(t) });
    }
    base.push({ id: "logout", group: "Preferences", label: "Sign out", icon: LogOut, run: logout });
    return base;
  }, [nav, can, memberships, tenant, setTenant, qc, theme, setTheme, logout, fire]);

  const results = useMemo(() => {
    const remote: Command[] = (hits.data ?? []).map((h) => ({
      id: `hit-${h.kind}-${h.id}`,
      group: HIT_GROUP[h.kind] ?? "Results",
      label: h.title,
      hint: h.subtitle,
      icon: HIT_ICON[h.kind] ?? Search,
      run: () => nav(h.href),
    }));
    const local = commands
      .map((c) => ({ c, s: rank(query, c) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .map((x) => x.c);
    const all = query.trim() ? [...remote, ...local] : local;
    const groups: { name: string; items: Command[] }[] = [];
    for (const c of all) {
      const g = groups.find((x) => x.name === c.group) ?? groups[groups.push({ name: c.group, items: [] }) - 1];
      g.items.push(c);
    }
    let offset = 0;
    const indexed = groups.map((g) => {
      const start = offset;
      offset += g.items.length;
      return { ...g, start };
    });
    return { groups: indexed, flat: groups.flatMap((g) => g.items) };
  }, [commands, hits.data, query, nav]);

  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  const choose = (c: Command | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };

  const onKey = (e: React.KeyboardEvent) => {
    const n = results.flat.length;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (n ? (a + 1) % n : 0));
    }
    else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (n ? (a - 1 + n) % n : 0));
    }
    else if (e.key === "Enter") {
      e.preventDefault();
      choose(results.flat[active]);
    }
    else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  const searching = deferred.length >= 2 && hits.isFetching;
  return (
    <div className="fixed inset-0 z-50 flex animate-[fade_180ms_ease-out] items-start justify-center bg-black/20 px-3 pt-[12vh]" onMouseDown={onClose} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKey}
        className="w-full max-w-[640px] animate-[pop_260ms_var(--ease-spring)] overflow-hidden rounded-[20px] bg-panel shadow-[var(--pop-shadow)]"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search size={18} className="shrink-0 text-ink-3" aria-hidden />
          <input
            ref={input}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Search runs, approvals, agents, or type a command"
            className="h-14 min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-ink-3 focus-visible:outline-none"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={results.flat[active] ? `${listId}-${active}` : undefined}
            aria-autocomplete="list"
          />
          {searching && <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-line-2 border-t-accent" aria-label="Searching" />}
          <Kbd>Esc</Kbd>
        </div>
        <div ref={list} id={listId} role="listbox" aria-label="Results" className="max-h-[min(60vh,440px)] overflow-y-auto p-2">
          {results.flat.length === 0 && (
            <p className="px-3 py-10 text-center text-sm text-ink-3">
              {searching ? "Searching…" : `Nothing matches “${query.trim()}”. Try a run title, a customer's name or a page.`}
            </p>
          )}
          {results.groups.map((g) => (
            <div key={g.name} role="group" aria-label={g.name} className="pb-1">
              <p className="px-3 pt-2.5 pb-1.5 text-xs font-medium text-ink-3">{g.name}</p>
              {g.items.map((c, j) => {
                const i = g.start + j;
                const on = i === active;
                return (
                  <div
                    key={c.id}
                    id={`${listId}-${i}`}
                    data-index={i}
                    role="option"
                    aria-selected={on}
                    onMouseMove={() => active !== i && setActive(i)}
                    onClick={() => choose(c)}
                    className={cx("flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5", on && "bg-sunk")}
                  >
                    <c.icon size={17} strokeWidth={1.8} className={cx("shrink-0", on ? "text-accent" : "text-ink-3")} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14.5px] text-ink">{c.label}</span>
                      {c.hint && <span className="block truncate text-[13px] text-ink-3">{c.hint}</span>}
                    </span>
                    {c.keys && (
                      <span className="flex shrink-0 gap-1">
                        {c.keys.map((k) => (
                          <Kbd key={k}>{k}</Kbd>
                        ))}
                      </span>
                    )}
                    {on && <CornerDownLeft size={14} className="shrink-0 text-ink-3" aria-hidden />}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-line px-4 py-2.5 text-xs text-ink-3">
          <span className="flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> to move
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>↵</Kbd> to open
          </span>
          <span className="ml-auto">Searches this workspace only</span>
        </div>
      </div>
    </div>
  );
}
