import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Check,
  CheckCircle2,
  ChevronsUpDown,
  FlaskConical,
  Gauge,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Plug,
  Route,
  Search,
  Settings as SettingsIcon,
  Sun,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { LogoMark } from "@/components/brand/Logo";
import { ActivityButton, StatusButton } from "@/components/chrome/Popovers";
import { CommandPalette } from "@/components/command/CommandPalette";
import { Avatar, ChromeContext, cx, Kbd } from "@/components/ui";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { useShortcuts } from "@/hooks/useShortcuts";
import { useTheme, type Theme } from "@/hooks/useTheme";

const NAV: { group?: string; items: { to: string; label: string; icon: typeof Gauge; end?: boolean; key: string }[] }[] = [
  {
    items: [
      { to: "/", label: "Overview", icon: Gauge, end: true, key: "O" },
      { to: "/runs", label: "Runs", icon: Route, key: "R" },
      { to: "/approvals", label: "Approvals", icon: CheckCircle2, key: "A" },
    ],
  },
  {
    group: "Build",
    items: [
      { to: "/agents", label: "Agents", icon: Bot, key: "E" },
      { to: "/workflows", label: "Workflows", icon: Workflow, key: "W" },
      { to: "/connectors", label: "Connectors", icon: Plug, key: "C" },
    ],
  },
  {
    group: "Test",
    items: [{ to: "/simulators", label: "Simulators", icon: FlaskConical, key: "S" }],
  },
];

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

function WorkspaceMenu() {
  const { memberships, tenant, setTenant } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Workspace: ${tenant?.name ?? "none"}. Switch workspace`}
        className="flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-fill active:bg-fill-2"
      >
        <LogoMark className="h-8 w-8" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-semibold tracking-[-0.016em]">{tenant?.name ?? "Oryn OS"}</span>
          <span className="block truncate text-[12px] text-ink-3 capitalize">{tenant?.role}</span>
        </span>
        <ChevronsUpDown size={14} className="shrink-0 text-ink-3" aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className="material absolute top-full right-0 left-0 z-30 mt-1.5 origin-top animate-[pop_220ms_var(--ease-spring)] rounded-[14px] p-1.5 shadow-[var(--pop-shadow)]"
        >
          {memberships.map((m) => (
            <button
              key={m.tenant_id}
              role="menuitemradio"
              aria-checked={m.tenant_id === tenant?.tenant_id}
              onClick={() => {
                setOpen(false);
                if (m.tenant_id !== tenant?.tenant_id) {
                  setTenant(m.tenant_id);
                  qc.clear();
                  nav("/");
                }
              }}
              className="flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-[14px] hover:bg-accent hover:text-white"
            >
              <span className="min-w-0 flex-1 truncate">{m.name}</span>
              {m.tenant_id === tenant?.tenant_id && <Check size={15} aria-hidden />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const THEMES: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "Auto" },
];

function navClass(isActive: boolean) {
  return cx(
    "group flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[14px] transition-colors",
    isActive ? "bg-fill-2 font-medium text-ink" : "text-ink-2 hover:bg-fill hover:text-ink",
  );
}

function Sidebar({ live, theme, setTheme }: { live: boolean; theme: Theme; setTheme: (t: Theme) => void }) {
  const { user, logout, tenant } = useAuth();
  const pending = useQuery({
    queryKey: ["approvals", "pending", tenant?.tenant_id],
    queryFn: () => api.get<S["ApprovalOut"][]>("/api/approvals", { status: "pending" }),
    enabled: !!tenant,
  });
  const pendingCount = pending.data?.length ?? 0;

  return (
    <div className="flex h-full flex-col gap-5 px-3 pt-3 pb-3">
      <WorkspaceMenu />
      <nav aria-label="Main" className="flex flex-1 flex-col gap-5 overflow-y-auto">
        {NAV.map((g, gi) => (
          <div key={gi}>
            {g.group && <p className="px-2.5 pb-1 text-[12px] font-semibold text-ink-3">{g.group}</p>}
            <div className="flex flex-col gap-px">
              {g.items.map(({ to, label, icon: Icon, end, key }) => (
                <NavLink key={to} to={to} end={end} title={`${label} (G then ${key})`} className={({ isActive }) => navClass(isActive)}>
                  <Icon size={17} strokeWidth={1.9} className="text-accent" aria-hidden />
                  <span>{label}</span>
                  {to === "/approvals" && pendingCount > 0 && (
                    <span className="ml-auto text-[13px] font-medium text-ink-3 tabular-nums" aria-label={`${pendingCount} pending`}>
                      {pendingCount}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
        <NavLink to="/settings" className={({ isActive }) => cx(navClass(isActive), "mt-auto")}>
          <SettingsIcon size={17} strokeWidth={1.9} className="text-ink-3" aria-hidden />
          Settings
        </NavLink>
      </nav>
      <div className="flex items-center gap-2.5 px-1">
        <Avatar name={user?.name ?? "?"} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium">{user?.name}</p>
          <p className="flex items-center gap-1.5 text-[12px] text-ink-3" title={live ? "Receiving live updates" : "Connecting to live updates"}>
            <span className={cx("inline-block h-1.5 w-1.5 rounded-full", live ? "bg-clear" : "bg-idle")} aria-hidden />
            {live ? "Live" : "Connecting"}
          </p>
        </div>
        <button onClick={logout} className="rounded-full p-1.5 text-ink-3 transition-colors hover:bg-fill hover:text-ink" aria-label="Sign out" title="Sign out">
          <LogOut size={15} aria-hidden />
        </button>
      </div>
      <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-0.5 rounded-[10px] bg-fill p-0.5">
        {THEMES.map((t) => (
          <button
            key={t.value}
            role="radio"
            aria-checked={theme === t.value}
            onClick={() => setTheme(t.value)}
            title={t.label}
            className={cx(
              "flex h-6 items-center justify-center gap-1 rounded-[8px] text-[12px] transition-colors",
              theme === t.value ? "bg-panel text-ink shadow-[0_1px_3px_rgb(0_0_0/0.12)]" : "text-ink-3 hover:text-ink",
            )}
          >
            <t.icon size={12} aria-hidden />
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const rows: [string, string[]][] = [
    ["Open the command menu", [isMac ? "⌘" : "Ctrl", "K"]],
    ["Search", ["/"]],
    ...NAV.flatMap((g) => g.items.map((i) => [`Go to ${i.label}`, ["G", i.key]] as [string, string[]])),
    ["Move through a list", ["J", "K"]],
    ["Approve or reject the selected approval", ["A", "R"]],
    ["Show this list", ["?"]],
  ];
  return (
    <div className="fixed inset-0 z-50 flex animate-[fade_200ms_ease-out] items-center justify-center bg-black/25 px-4" onMouseDown={onClose} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        onMouseDown={(e) => e.stopPropagation()}
        className="w-full max-w-md animate-[pop_260ms_var(--ease-spring)] rounded-[22px] bg-panel p-6 shadow-[var(--pop-shadow)]"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[20px] font-bold tracking-[-0.022em]">Keyboard shortcuts</h2>
          <button onClick={onClose} className="flex h-7 w-7 items-center justify-center rounded-full bg-sunk text-ink-3 hover:text-ink" aria-label="Close">
            <X size={14} strokeWidth={2.5} />
          </button>
        </div>
        <dl className="divide-y divide-line text-[14px]">
          {rows.map(([label, keys]) => (
            <div key={label} className="flex items-center justify-between py-2">
              <dt className="text-ink-2">{label}</dt>
              <dd className="flex gap-1">
                {keys.map((k) => (
                  <Kbd key={k}>{k}</Kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

export function Layout() {
  const { tenant, token } = useAuth();
  const { connected } = useLiveEvents({ tenantId: tenant?.tenant_id ?? null, token });
  const { theme, setTheme } = useTheme();
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [title, setTitle] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  // The mobile menu belongs to the page it was opened on, so navigating closes it without an effect.
  const [mobileNavAt, setMobileNavAt] = useState<string | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const main = useRef<HTMLElement>(null);
  const mobileNav = mobileNavAt === loc.pathname;
  const chrome = useMemo(() => ({ setTitle, setCollapsed }), []);

  useEffect(() => {
    main.current?.scrollTo({ top: 0 });
  }, [loc.pathname]);

  const go = Object.fromEntries(NAV.flatMap((g) => g.items).map((i) => [i.key.toLowerCase(), () => nav(i.to)]));
  useShortcuts({ onPalette: () => setPalette((p) => !p), onHelp: () => setHelp(true), go });

  const sidebar = <Sidebar live={connected} theme={theme} setTheme={setTheme} />;
  return (
    <ChromeContext.Provider value={chrome}>
      <div className="h-dvh bg-paper md:grid md:grid-cols-[248px_1fr]">
        <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-panel focus:px-3 focus:py-2">
          Skip to content
        </a>
        <aside className="hidden h-dvh border-r border-line/70 md:block">{sidebar}</aside>

        {mobileNav && (
          <div className="fixed inset-0 z-40 animate-[fade_200ms_ease-out] bg-black/25 md:hidden" onClick={() => setMobileNavAt(null)} role="presentation">
            <aside className="material h-full w-[284px] animate-[slide-in_360ms_var(--ease-spring)] shadow-xl" onClick={(e) => e.stopPropagation()}>
              {sidebar}
            </aside>
          </div>
        )}

        <main ref={main} id="content" className="relative h-dvh min-w-0 overflow-y-auto">
          <div
            className={cx(
              "sticky top-0 z-30 flex h-[52px] items-center gap-2 px-3 transition-[background-color,box-shadow] duration-200 md:px-6",
              collapsed ? "material shadow-[0_0.5px_0_var(--line)]" : "bg-transparent",
            )}
          >
            <button onClick={() => setMobileNavAt(loc.pathname)} className="rounded-full p-2 text-ink-2 hover:bg-sunk md:hidden" aria-label="Open menu">
              <Menu size={19} />
            </button>
            <p
              aria-hidden={!collapsed}
              className={cx(
                "min-w-0 flex-1 truncate text-[15px] font-semibold tracking-[-0.016em] transition-[opacity,transform] duration-200",
                collapsed ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0",
              )}
            >
              {title}
            </p>
            <button
              onClick={() => setPalette(true)}
              className="flex h-9 items-center gap-2 rounded-full px-3 text-[13px] text-ink-3 transition-colors hover:bg-sunk hover:text-ink sm:w-56 sm:bg-fill"
              aria-label="Search"
            >
              <Search size={15} aria-hidden />
              <span className="hidden flex-1 text-left sm:inline">Search</span>
              <span className="hidden text-[12px] sm:inline">{isMac ? "⌘K" : "Ctrl K"}</span>
            </button>
            <StatusButton />
            <ActivityButton />
          </div>
          <div key={loc.pathname} className="mx-auto max-w-[1160px] animate-[fade_240ms_ease-out] px-5 pt-2 pb-16 md:px-10">
            <Outlet />
          </div>
        </main>

        {palette && <CommandPalette onClose={() => setPalette(false)} theme={theme} setTheme={setTheme} />}
        {help && <ShortcutsDialog onClose={() => setHelp(false)} />}
      </div>
    </ChromeContext.Provider>
  );
}
