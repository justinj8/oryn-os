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
import { IconTile, type TileColor } from "@/components/brand/IconTile";
import { LogoMark } from "@/components/brand/Logo";
import { ActivityButton, StatusButton } from "@/components/chrome/Popovers";
import { ThemeToggle } from "@/components/chrome/ThemeToggle";
import { CommandPalette } from "@/components/command/CommandPalette";
import { Avatar, ChromeContext, cx, Kbd } from "@/components/ui";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { useShortcuts } from "@/hooks/useShortcuts";
import { useTheme, type Theme } from "@/hooks/useTheme";

type NavItem = { to: string; label: string; icon: typeof Gauge; end?: boolean; key: string; color: TileColor };
const NAV: { group?: string; items: NavItem[] }[] = [
  {
    items: [
      { to: "/", label: "Overview", icon: Gauge, end: true, key: "O", color: "indigo" },
      { to: "/runs", label: "Runs", icon: Route, key: "R", color: "blue" },
      { to: "/approvals", label: "Approvals", icon: CheckCircle2, key: "A", color: "orange" },
    ],
  },
  {
    group: "Build",
    items: [
      { to: "/agents", label: "Agents", icon: Bot, key: "E", color: "purple" },
      { to: "/workflows", label: "Workflows", icon: Workflow, key: "W", color: "teal" },
      { to: "/connectors", label: "Connectors", icon: Plug, key: "C", color: "green" },
    ],
  },
  {
    group: "Test",
    items: [{ to: "/simulators", label: "Simulators", icon: FlaskConical, key: "S", color: "pink" }],
  },
];

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
/** Views laid out as panes (list and inspector) fill the window and scroll inside their panes. */
const PANES = /^\/(runs|approvals)(\/|$)/;

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
        className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-fill"
      >
        <LogoMark className="h-7 w-7" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-semibold tracking-[-0.01em]">{tenant?.name ?? "Oryn OS"}</span>
          <span className="block truncate text-[11px] text-ink-3 capitalize">{tenant?.role}</span>
        </span>
        <ChevronsUpDown size={13} className="shrink-0 text-ink-3" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="material absolute top-full right-0 left-0 z-30 mt-1 origin-top animate-[pop_200ms_var(--ease-spring)] rounded-xl p-1 shadow-[var(--pop-shadow)]">
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
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-select hover:text-white"
            >
              <span className="min-w-0 flex-1 truncate">{m.name}</span>
              {m.tenant_id === tenant?.tenant_id && <Check size={13} aria-hidden />}
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
    "flex h-[30px] items-center gap-2 rounded-md px-1.5 text-[13px] transition-colors",
    isActive ? "bg-fill-2 font-medium text-ink" : "text-ink-2 hover:bg-fill",
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
    <div className="flex h-full flex-col gap-4 px-2.5 pt-2.5 pb-2.5">
      <WorkspaceMenu />
      <nav aria-label="Main" className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {NAV.map((g, gi) => (
          <div key={gi}>
            {g.group && <p className="px-2 pb-1 text-[11px] font-semibold text-ink-3">{g.group}</p>}
            <div className="flex flex-col gap-px">
              {g.items.map(({ to, label, icon, end, key, color }) => (
                <NavLink key={to} to={to} end={end} title={`${label} (G then ${key})`} className={({ isActive }) => navClass(isActive)}>
                  <IconTile icon={icon} color={color} size={20} />
                  <span>{label}</span>
                  {to === "/approvals" && pendingCount > 0 && (
                    <span className="ml-auto rounded-full bg-hold px-1.5 text-[11px] font-semibold text-white tabular-nums" aria-label={`${pendingCount} pending`}>
                      {pendingCount}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
        <NavLink to="/settings" className={({ isActive }) => cx(navClass(isActive), "mt-auto")}>
          <IconTile icon={SettingsIcon} color="gray" size={20} />
          Settings
        </NavLink>
      </nav>
      <div className="flex items-center gap-2 px-1">
        <Avatar name={user?.name ?? "?"} className="h-7 w-7 text-[11px]" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12.5px] font-medium">{user?.name}</p>
          <p className="flex items-center gap-1.5 text-[11px] text-ink-3" title={live ? "Receiving live updates" : "Connecting to live updates"}>
            <span className={cx("inline-block h-1.5 w-1.5 rounded-full", live ? "bg-clear" : "bg-idle")} aria-hidden />
            {live ? "Live" : "Connecting"}
          </p>
        </div>
        <button onClick={logout} className="rounded-md p-1.5 text-ink-3 transition-colors hover:bg-fill hover:text-ink" aria-label="Sign out" title="Sign out">
          <LogOut size={14} aria-hidden />
        </button>
      </div>
      <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-0.5 rounded-lg bg-fill p-0.5">
        {THEMES.map((t) => (
          <button
            key={t.value}
            role="radio"
            aria-checked={theme === t.value}
            onClick={() => setTheme(t.value)}
            title={t.label}
            className={cx(
              "flex h-[22px] items-center justify-center gap-1 rounded-md text-[11px] transition-colors",
              theme === t.value ? "bg-panel text-ink shadow-[0_1px_2px_rgb(0_0_0/0.14)]" : "text-ink-3 hover:text-ink",
            )}
          >
            <t.icon size={11} aria-hidden />
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
    ["Approve or reject the selected request", ["A", "R"]],
    ["Show this list", ["?"]],
  ];
  return (
    <div className="fixed inset-0 z-50 flex animate-[fade_200ms_ease-out] items-center justify-center bg-black/25 px-4" onMouseDown={onClose} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        onMouseDown={(e) => e.stopPropagation()}
        className="w-full max-w-sm animate-[pop_240ms_var(--ease-spring)] rounded-2xl bg-panel p-5 shadow-[var(--pop-shadow)]"
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold">Keyboard shortcuts</h2>
          <button onClick={onClose} className="flex h-6 w-6 items-center justify-center rounded-full bg-fill text-ink-3 hover:text-ink" aria-label="Close">
            <X size={12} strokeWidth={2.5} />
          </button>
        </div>
        <dl className="divide-y divide-line text-[13px]">
          {rows.map(([label, keys]) => (
            <div key={label} className="flex items-center justify-between py-1.5">
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
  // The mobile menu belongs to the page it was opened on, so navigating closes it without an effect.
  const [mobileNavAt, setMobileNavAt] = useState<string | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const scroller = useRef<HTMLDivElement>(null);
  const mobileNav = mobileNavAt === loc.pathname;
  const panes = PANES.test(loc.pathname);
  const section = loc.pathname.split("/")[1];

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
  }, [section]);

  const go = Object.fromEntries(NAV.flatMap((g) => g.items).map((i) => [i.key.toLowerCase(), () => nav(i.to)]));
  useShortcuts({ onPalette: () => setPalette((p) => !p), onHelp: () => setHelp(true), go });

  const chrome = useMemo(
    () => ({
      toolbar: (
        <>
          <button
            onClick={() => setPalette(true)}
            className="flex h-7 items-center gap-1.5 rounded-md px-2 text-[12.5px] text-ink-3 transition-colors hover:bg-fill hover:text-ink lg:w-44 lg:bg-fill"
            aria-label="Search"
          >
            <Search size={13} aria-hidden />
            <span className="hidden flex-1 text-left lg:inline">Search</span>
            <span className="hidden text-[11px] lg:inline">{isMac ? "⌘K" : "Ctrl K"}</span>
          </button>
          <StatusButton />
          <ThemeToggle />
          <ActivityButton />
        </>
      ),
    }),
    [],
  );

  const sidebar = <Sidebar live={connected} theme={theme} setTheme={setTheme} />;
  return (
    <ChromeContext.Provider value={chrome}>
      <div className="h-dvh md:grid md:grid-cols-[232px_1fr]">
        <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-panel focus:px-3 focus:py-2">
          Skip to content
        </a>
        <aside className="hidden h-dvh border-r border-line/70 bg-sidebar backdrop-blur-2xl backdrop-saturate-150 md:block">{sidebar}</aside>

        {mobileNav && (
          <div className="fixed inset-0 z-40 animate-[fade_200ms_ease-out] bg-black/25 md:hidden" onClick={() => setMobileNavAt(null)} role="presentation">
            <aside className="material h-full w-[272px] animate-[slide-in_340ms_var(--ease-spring)] shadow-xl" onClick={(e) => e.stopPropagation()}>
              {sidebar}
            </aside>
          </div>
        )}

        <main id="content" className="glass relative flex h-dvh min-w-0 flex-col">
          <button
            onClick={() => setMobileNavAt(loc.pathname)}
            className="absolute top-2.5 left-2 z-30 rounded-md p-1.5 text-ink-2 hover:bg-fill md:hidden"
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>
          {panes ? (
            <div key={section} className="flex min-h-0 flex-1 animate-[fade_200ms_ease-out]">
              <Outlet />
            </div>
          ) : (
            <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
              <div key={section} className="animate-[fade_200ms_ease-out] px-5 pb-16 md:px-8">
                <Outlet />
              </div>
            </div>
          )}
        </main>

        {palette && <CommandPalette onClose={() => setPalette(false)} theme={theme} setTheme={setTheme} />}
        {help && <ShortcutsDialog onClose={() => setHelp(false)} />}
      </div>
    </ChromeContext.Provider>
  );
}
