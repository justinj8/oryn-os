import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setAuth, setUnauthorizedHandler, type S } from "@/api/client";
import { load, save } from "./storage";

type Membership = S["MembershipOut"];
type Role = "viewer" | "operator" | "admin" | "owner";
const RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2, owner: 3 };

type AuthState = {
  token: string | null;
  user: S["UserOut"] | null;
  memberships: Membership[];
  tenant: Membership | null;
  role: Role | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setTenant: (tenantId: string) => void;
  can: (minimum: Role) => boolean;
};

const Ctx = createContext<AuthState | null>(null);
const K = { token: "oryn.token", tenant: "oryn.tenant", session: "oryn.session" };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => load(K.token));
  const [session, setSession] = useState<{ user: S["UserOut"]; memberships: Membership[] } | null>(() => {
    const raw = load(K.session);
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [tenantId, setTenantId] = useState<string | null>(() => load(K.tenant));
  setAuth({ token, tenantId });

  const logout = useCallback(() => {
    setToken(null);
    setSession(null);
    setTenantId(null);
    setAuth({ token: null, tenantId: null });
    [K.token, K.tenant, K.session].forEach((k) => save(k, null));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const s = await api.post<S["SessionOut"]>("/api/auth/login", { email, password });
    const first = s.memberships[0]?.tenant_id ?? null;
    const keep = s.memberships.some((m) => m.tenant_id === load(K.tenant)) ? load(K.tenant) : first;
    setAuth({ token: s.access_token, tenantId: keep });
    setToken(s.access_token);
    setSession({ user: s.user, memberships: s.memberships });
    setTenantId(keep);
    save(K.token, s.access_token);
    save(K.session, JSON.stringify({ user: s.user, memberships: s.memberships }));
    save(K.tenant, keep);
  }, []);

  const setTenant = useCallback((id: string) => {
    setTenantId(id);
    setAuth({ tenantId: id });
    save(K.tenant, id);
  }, []);

  const value = useMemo<AuthState>(() => {
    const memberships = session?.memberships ?? [];
    const tenant = memberships.find((m) => m.tenant_id === tenantId) ?? null;
    const role = (tenant?.role as Role | undefined) ?? null;
    return {
      token,
      user: token ? (session?.user ?? null) : null,
      memberships,
      tenant,
      role,
      login,
      logout,
      setTenant,
      can: (minimum: Role) => role !== null && RANK[role] >= RANK[minimum],
    };
  }, [token, session, tenantId, login, logout, setTenant]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
