import type { components } from "./schema";

export type S = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : describe(detail) ?? `Request failed (${status})`);
  }
}

function describe(detail: unknown): string | null {
  if (detail && typeof detail === "object" && "errors" in detail && Array.isArray((detail as { errors: unknown[] }).errors)) {
    return (detail as { errors: string[] }).errors.join("; ");
  }
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? String(d)).join("; ");
  return null;
}

type Auth = { token: string | null; tenantId: string | null };
const auth: Auth = { token: null, tenantId: null };
let onUnauthorized: (() => void) | null = null;

export function setAuth(next: Partial<Auth>) {
  Object.assign(auth, next);
}
export function getAuth(): Auth {
  return { ...auth };
}
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

type Query = Record<string, string | number | boolean | null | undefined>;

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; headers?: Record<string, string> } = {}): Promise<T> {
  const qs = opts.query
    ? "?" +
      new URLSearchParams(
        Object.entries(opts.query)
          .filter(([, v]) => v !== undefined && v !== null && v !== "")
          .map(([k, v]) => [k, String(v)]),
      ).toString()
    : "";
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  if (auth.tenantId) headers["X-Tenant-Id"] = auth.tenantId;
  const res = await fetch(path + (qs === "?" ? "" : qs), {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    if (res.status === 401 && auth.token) onUnauthorized?.();
    throw new ApiError(res.status, data?.detail ?? data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, { body: body ?? {}, headers }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  del: <T = void>(path: string) => request<T>("DELETE", path),
};
