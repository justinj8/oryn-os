import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Gauge,
  LogOut,
  MessagesSquare,
  Plug,
  Radio,
  Route,
  Settings as SettingsIcon,
  Workflow,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { cx } from "@/components/ui";
import { useLiveEvents } from "@/hooks/useLiveEvents";

const NAV = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/runs", label: "Runs", icon: Route },
  { to: "/approvals", label: "Approvals", icon: CheckCircle2 },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/workflows", label: "Workflows", icon: Workflow },
  { to: "/connectors", label: "Connectors", icon: Plug },
  { to: "/simulators", label: "Simulators", icon: MessagesSquare },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Layout() {
  const { user, tenant, memberships, setTenant, logout, role, token } = useAuth();
  useLiveEvents({ tenantId: tenant?.tenant_id ?? null, token });
  const pending = useQuery({
    queryKey: ["approvals", "pending", tenant?.tenant_id],
    queryFn: () => api.get<S["ApprovalOut"][]>("/api/approvals", { status: "pending" }),
    enabled: !!tenant,
  });
  const pendingCount = pending.data?.length ?? 0;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_1fr]">
      <aside className="bg-rail text-rail-ink">
        <div className="md:sticky md:top-0 md:h-screen md:overflow-y-auto">
        <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="font-display text-xl font-semibold text-white">Oryn OS</span>
        </div>
        <div className="px-3 pb-3">
          <label htmlFor="tenant" className="sr-only">
            Business
          </label>
          <select
            id="tenant"
            value={tenant?.tenant_id ?? ""}
            onChange={(e) => setTenant(e.target.value)}
            className="w-full rounded-md border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-white"
          >
            {memberships.map((m) => (
              <option key={m.tenant_id} value={m.tenant_id} className="text-ink">
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-2 pb-3 md:flex-col md:overflow-visible">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cx(
                  "flex shrink-0 items-center gap-2.5 rounded-md px-2.5 py-2 text-sm",
                  isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white",
                )
              }
            >
              <Icon size={17} strokeWidth={1.8} aria-hidden />
              <span>{label}</span>
              {to === "/approvals" && pendingCount > 0 && (
                <span className="ml-auto rounded-full bg-hold px-1.5 text-xs font-semibold text-rail" aria-label={`${pendingCount} pending`}>
                  {pendingCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t border-white/10 px-4 py-3 text-sm md:block">
          <p className="flex items-center gap-1.5 text-xs text-rail-ink">
            <Radio size={13} className="text-clear" aria-hidden /> Live updates on
          </p>
          <p className="mt-2 truncate text-white">{user?.name}</p>
          <p className="text-xs capitalize">{role}</p>
          <button onClick={logout} className="mt-2 inline-flex items-center gap-1.5 text-xs hover:text-white">
            <LogOut size={13} aria-hidden /> Sign out
          </button>
        </div>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
