import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { api } from "@/api/client";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";

const session = {
  access_token: "tok-123",
  user: { id: "u1", email: "owner@northwind.test", name: "Olivia Owner" },
  memberships: [
    { tenant_id: "t-north", slug: "northwind", name: "Northwind HVAC", role: "owner" },
    { tenant_id: "t-bright", slug: "brightsmile", name: "Brightsmile Dental", role: "viewer" },
  ],
};

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

const wrapper = ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>;

test("login stores token and memberships and selects the first tenant", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json(session));
  const { result } = renderHook(() => useAuth(), { wrapper });
  await act(() => result.current.login("owner@northwind.test", "oryn-demo"));
  expect(result.current.user?.name).toBe("Olivia Owner");
  expect(result.current.tenant?.slug).toBe("northwind");
  expect(result.current.role).toBe("owner");
  expect(localStorage.getItem("oryn.token")).toBe("tok-123");
});

test("setTenant persists and is sent as X-Tenant-Id", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(session));
  const { result } = renderHook(() => useAuth(), { wrapper });
  await act(() => result.current.login("owner@northwind.test", "oryn-demo"));
  act(() => result.current.setTenant("t-bright"));
  expect(localStorage.getItem("oryn.tenant")).toBe("t-bright");
  expect(result.current.role).toBe("viewer");
  fetchMock.mockImplementation(() => json([]));
  await api.get("/api/agents");
  const headers = new Headers(fetchMock.mock.calls.at(-1)![1]!.headers);
  expect(headers.get("X-Tenant-Id")).toBe("t-bright");
  expect(headers.get("Authorization")).toBe("Bearer tok-123");
});

test("a 401 logs the user out", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(session));
  const { result } = renderHook(() => useAuth(), { wrapper });
  await act(() => result.current.login("owner@northwind.test", "oryn-demo"));
  fetchMock.mockImplementation(() => json({ detail: "invalid token" }, 401));
  await expect(api.get("/api/agents")).rejects.toThrow();
  await waitFor(() => expect(result.current.user).toBeNull());
  expect(localStorage.getItem("oryn.token")).toBeNull();
});

test("login failure surfaces the API message", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ detail: "invalid email or password" }, 401));
  const { result } = renderHook(() => useAuth(), { wrapper });
  await expect(act(() => result.current.login("x@y.z", "nope"))).rejects.toThrow("invalid email or password");
});
