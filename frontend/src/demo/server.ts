/**
 * Demo mode: the whole API, played in the browser from a recording of a real stack.
 *
 * The hosted build (VITE_DEMO=1) has no backend. Reads come from src/demo/snapshot.json, recorded
 * from a running Oryn OS by scripts/record-demo.mjs, with every timestamp shifted so the data looks
 * current. Writes are simulated faithfully enough to feel real: a test lead walks through the same
 * agent steps a recorded run took, stops for approval, and finishes once someone decides.
 */
import type { S } from "@/api/client";
import raw from "./snapshot.json";

type Run = S["RunOut"];
type Detail = S["RunDetail"];
type Span = S["SpanOut"];
type Approval = S["ApprovalOut"];
type Snapshot = {
  capturedAt: string;
  tenant: S["MembershipOut"];
  user: S["UserOut"];
  get: Record<string, unknown>;
  runs: Record<string, { summary: Run; detail: Detail; spans: Span[] }>;
  drafts: Record<string, unknown>;
  chat: unknown;
};
type Query = Record<string, string | number | boolean | null | undefined>;

export class DemoError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

// ---- time shift: make the recording look like it happened just now --------------------------------

const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
function shifted<T>(value: T, ms: number, days: number): T {
  if (typeof value === "string") {
    if (ISO.test(value)) return new Date(new Date(value).getTime() + ms).toISOString() as T;
    if (DAY.test(value)) {
      const d = new Date(value + "T00:00:00Z");
      d.setUTCDate(d.getUTCDate() + days);
      return d.toISOString().slice(0, 10) as T;
    }
    return value;
  }
  if (Array.isArray(value)) return value.map((v) => shifted(v, ms, days)) as T;
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shifted(v, ms, days)])) as T;
  return value;
}

const snap = raw as unknown as Snapshot;
const offset = Date.now() - new Date(snap.capturedAt).getTime();
const data: Snapshot = shifted(snap, offset, Math.round(offset / 86_400_000));

// ---- the in-memory world --------------------------------------------------------------------------

type Entry = { summary: Run; detail: Detail; spans: Span[] };
const runs = new Map<string, Entry>(Object.entries(data.runs));
let approvals: Approval[] = (data.get["/api/approvals"] as Approval[]) ?? [];
const lists: Record<string, unknown[]> = {};
for (const k of ["/api/agents", "/api/workflows", "/api/connectors", "/api/members", "/api/api-keys", "/api/memories"]) lists[k] = [...((data.get[k] as unknown[]) ?? [])];
let traffic = { enabled: false, rate_per_min: 4 };

const ROLES = ["viewer", "operator", "admin", "owner"] as const;
type Role = (typeof ROLES)[number];
let session: { email: string; role: Role; userId: string } | null = null;
const rank = (r: string) => ROLES.indexOf(r as Role);

// ---- live events ----------------------------------------------------------------------------------

export type DemoEvent = { type: string; run_id: string | null };
const listeners = new Set<(e: DemoEvent) => void>();
export function onDemoEvent(fn: (e: DemoEvent) => void) {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}
const emit = (type: string, run_id: string | null = null) => listeners.forEach((fn) => fn({ type, run_id }));

// ---- helpers --------------------------------------------------------------------------------------

const now = () => new Date().toISOString();
const uuid = () => crypto.randomUUID();
const ordered = () => [...runs.values()].sort((a, b) => b.summary.started_at.localeCompare(a.summary.started_at));
const matches = (title: string, q: unknown) => !q || title.toLowerCase().includes(String(q).trim().toLowerCase());

function route(spans: Span[]): string[] {
  const out: string[] = [];
  for (const s of [...spans].sort((a, b) => a.started_at.localeCompare(b.started_at))) {
    if (s.kind !== "agent") continue;
    const agent = s.name.split(" · ")[0];
    if (out[out.length - 1] !== agent) out.push(agent);
  }
  return out;
}

function sync(e: Entry) {
  const ended = e.detail.ended_at;
  e.detail.duration_s = ended ? (new Date(ended).getTime() - new Date(e.detail.started_at).getTime()) / 1000 : null;
  e.detail.total_cost_usd = String(e.spans.reduce((s, x) => s + Number(x.cost_usd), 0).toFixed(6));
  e.detail.total_input_tokens = e.spans.reduce((s, x) => s + x.input_tokens, 0);
  e.detail.total_output_tokens = e.spans.reduce((s, x) => s + x.output_tokens, 0);
  e.detail.approvals = approvals.filter((a) => a.run_id === e.detail.id);
  const d = e.detail;
  e.summary = {
    id: d.id,
    title: d.title,
    kind: d.kind,
    status: d.status,
    workflow_id: d.workflow_id,
    started_at: d.started_at,
    ended_at: d.ended_at,
    duration_s: d.duration_s,
    total_input_tokens: d.total_input_tokens,
    total_output_tokens: d.total_output_tokens,
    total_cost_usd: d.total_cost_usd,
    simulated_cost: d.simulated_cost,
    outcome_summary: d.outcome_summary,
    error: d.error,
    temporal_workflow_id: d.temporal_workflow_id,
    rerunnable: d.rerunnable,
    route: route(e.spans),
  };
}

// ---- simulated runs: replay a recorded run's steps in real time ------------------------------------

/** Text borrowed from a recorded run names that run's customer; swap in this run's. */
function retell<T>(value: T, from: string, to: string): T {
  if (!from || !to || from === to) return value;
  return JSON.parse(JSON.stringify(value).split(from).join(to)) as T;
}
const customer = (title: string) => title.split(" for ").slice(1).join(" for ");

/** The recorded run whose steps a new run will follow: same workflow, preferring one that finished well. */
function template(workflowId: string | null, wantApproval: boolean): Entry | undefined {
  const same = ordered().filter((e) => e.summary.workflow_id === workflowId && e.detail.kind === "workflow");
  return (
    same.find((e) => e.summary.status === "completed" && e.detail.approvals.length > 0 === wantApproval) ??
    same.find((e) => e.summary.status === "completed") ??
    same[0]
  );
}

function workflowFor(type: string) {
  return (lists["/api/workflows"] as S["WorkflowOut"][]).find((w) => w.trigger_event === type && w.enabled);
}

function startFrom(t: Entry, title: string, workflowId: string | null): string {
  const id = uuid();
  const t0 = Date.now();
  const base = new Date(t.detail.started_at).getTime();
  // Replay at a watchable pace: the whole recorded run is squeezed into a few seconds.
  const recorded = Math.max(...t.spans.map((s) => new Date(s.ended_at ?? s.started_at).getTime() - base), 1);
  const scale = Math.min(1, 4500 / recorded);
  const at = (iso: string) => t0 + (new Date(iso).getTime() - base) * scale;
  const idMap = new Map(t.spans.map((s) => [s.id, uuid()]));
  const plan = [...t.spans]
    .sort((a, b) => a.started_at.localeCompare(b.started_at))
    .map((s) => ({ ...s, id: idMap.get(s.id)!, parent_span_id: s.parent_span_id ? (idMap.get(s.parent_span_id) ?? null) : null, start: at(s.started_at), end: s.ended_at ? at(s.ended_at) : null }));
  const pause = plan.find((s) => s.kind === "approval");
  const recordedApproval = t.detail.approvals[0];

  const e: Entry = {
    spans: [],
    summary: {} as Run,
    detail: {
      ...t.detail,
      id,
      title,
      workflow_id: workflowId,
      status: "running",
      started_at: new Date(t0).toISOString(),
      ended_at: null,
      error: null,
      outcome_summary: null,
      outcomes: [],
      blackboard: {},
      approvals: [],
      temporal_workflow_id: `demo-${id}`,
      rerunnable: true,
      live_state: null,
    },
  };
  runs.set(id, e);
  sync(e);
  emit("run.started", id);

  const reveal = (until: number, offsetMs: number) => {
    for (const s of plan) {
      if (s.start > until || e.spans.some((x) => x.id === s.id)) continue;
      const { start, end, ...span } = s;
      e.spans.push({ ...span, started_at: new Date(start + offsetMs).toISOString(), ended_at: end ? new Date(end + offsetMs).toISOString() : null });
    }
    sync(e);
    emit("span.ended", id);
  };
  // Step through the plan in real time, a few spans per tick.
  const stepTo = (limit: number, offsetMs: number, done: () => void) => {
    const tick = () => {
      const t = Date.now() - offsetMs;
      reveal(Math.min(t, limit), offsetMs);
      if (t >= limit) done();
      else setTimeout(tick, 350);
    };
    tick();
  };

  const finish = (offsetMs: number) => {
    stepTo(Math.max(...plan.map((s) => s.end ?? s.start)), offsetMs, () => {
      e.detail.status = t.detail.status === "waiting_approval" || t.detail.status === "running" ? "completed" : t.detail.status;
      e.detail.ended_at = now();
      const [from, to] = [customer(t.detail.title), customer(title)];
      e.detail.outcome_summary = e.detail.outcome_summary ?? retell(t.detail.outcome_summary, from, to);
      e.detail.outcomes = t.detail.outcomes.map((o) => ({ ...o, occurred_at: now() }));
      e.detail.blackboard = retell(t.detail.blackboard, from, to);
      e.detail.error = t.detail.error;
      sync(e);
      emit("run.updated", id);
    });
  };

  if (pause && recordedApproval) {
    stepTo(pause.end ?? pause.start, 0, () => {
      e.detail.status = "waiting_approval";
      const a: Approval = { ...recordedApproval, id: uuid(), run_id: id, run_title: title, status: "pending", requested_at: now(), decided_at: null, decided_by: null, comment: null, escalation_level: 0 };
      approvals = [a, ...approvals];
      sync(e);
      emit("approval.requested", id);
      emit("run.updated", id);
      resumeAfter.set(a.id, (approved: boolean) => {
        e.detail.status = "running";
        sync(e);
        emit("run.updated", id);
        // Continue from where it paused, on the clock as it is now.
        const shiftMs = Date.now() - (pause.end ?? pause.start);
        if (!approved) e.detail.outcome_summary = "Continued without the discount.";
        finish(shiftMs);
      });
    });
  } else {
    finish(0);
  }
  return id;
}
const resumeAfter = new Map<string, (approved: boolean) => void>();

/**
 * A run that was waiting in the recording itself: finish it with the steps a recorded run of the
 * same workflow took after its approval, replayed from now.
 */
function continueRecorded(e: Entry, approved: boolean) {
  const t = template(e.summary.workflow_id, true);
  const pause = t?.spans.find((s) => s.kind === "approval");
  const afterAt = pause ? new Date(pause.ended_at ?? pause.started_at).getTime() : 0;
  const rest = (t?.spans ?? []).filter((s) => new Date(s.started_at).getTime() >= afterAt).sort((a, b) => a.started_at.localeCompare(b.started_at));
  const root = e.spans.find((s) => !s.parent_span_id)?.id ?? null;
  const t0 = Date.now();
  const scale = Math.min(1, 3000 / Math.max(1, ...rest.map((s) => new Date(s.ended_at ?? s.started_at).getTime() - afterAt)));
  const at = (iso: string) => new Date(t0 + (new Date(iso).getTime() - afterAt) * scale).toISOString();
  e.detail.status = "running";
  sync(e);
  emit("run.updated", e.detail.id);
  const ids = new Map(rest.map((s) => [s.id, uuid()]));
  rest.forEach((s, i) => {
    setTimeout(() => {
      e.spans.push({ ...s, id: ids.get(s.id)!, parent_span_id: s.parent_span_id ? (ids.get(s.parent_span_id) ?? root) : root, started_at: at(s.started_at), ended_at: s.ended_at ? at(s.ended_at) : null });
      sync(e);
      emit("span.ended", e.detail.id);
    }, 250 + i * (2800 / Math.max(rest.length, 1)));
  });
  setTimeout(() => {
    e.detail.status = "completed";
    e.detail.ended_at = now();
    e.detail.outcomes = (t?.detail.outcomes ?? []).map((o) => ({ ...o, occurred_at: now() }));
    e.detail.outcome_summary = t ? retell(t.detail.outcome_summary, customer(t.detail.title), customer(e.detail.title)) : approved ? "Approved and completed." : "Continued without the discount.";
    sync(e);
    emit("run.updated", e.detail.id);
  }, 3400);
}

function fire(type: string, payload: Record<string, unknown>): string[] {
  const wf = workflowFor(type);
  if (!wf) return [];
  const wantApproval = Number(payload.requested_discount_pct ?? 0) > 10 || /refund/i.test(String(payload.subject ?? ""));
  const t = template(wf.id, wantApproval);
  if (!t) return [];
  const who = payload.name ?? payload.company ?? payload.email ?? payload.subject;
  return [startFrom(t, who ? `${wf.name} for ${who}` : wf.name, wf.id)];
}

// Live traffic: when switched on, new work keeps arriving like it would from real customers.
const SAMPLE = [
  { type: "lead.created", payload: { name: "Ari Patel", budget_usd: 9200, requested_discount_pct: 15 } },
  { type: "lead.created", payload: { name: "Noah Kim", budget_usd: 700 } },
  { type: "ticket.created", payload: { name: "Lena Ortiz", subject: "Thermostat question" } },
  { type: "invoice.overdue", payload: {} },
];
let trafficTimer: ReturnType<typeof setTimeout> | undefined;
function scheduleTraffic() {
  clearTimeout(trafficTimer);
  if (!traffic.enabled) return;
  trafficTimer = setTimeout(() => {
    const s = SAMPLE[Math.floor(Math.random() * SAMPLE.length)];
    fire(s.type, s.payload);
    scheduleTraffic();
  }, 60_000 / traffic.rate_per_min);
}

// ---- derived reads --------------------------------------------------------------------------------

function activity(limit: number, before?: string) {
  const items: S["ActivityItem"][] = [];
  for (const a of approvals) {
    const title = runs.get(a.run_id)?.detail.title ?? a.run_title ?? "";
    items.push({ id: `approval_requested:${a.id}`, kind: "approval_requested", at: a.requested_at, title: a.description, detail: title, href: a.status === "pending" ? `/approvals/${a.id}` : `/runs/${a.run_id}`, tone: "hold", value_usd: null });
    if (a.decided_at)
      items.push({
        id: `approval_decided:${a.id}`,
        kind: "approval_decided",
        at: a.decided_at,
        title: `${a.status.charAt(0).toUpperCase()}${a.status.slice(1)}: ${a.description}`,
        detail: a.comment ?? title,
        href: `/runs/${a.run_id}`,
        tone: a.status === "approved" ? "clear" : "neutral",
        value_usd: null,
      });
  }
  for (const { detail: r } of runs.values()) {
    if (r.status === "failed" || r.status === "escalated")
      items.push({ id: `run:${r.id}`, kind: r.status === "failed" ? "run_failed" : "run_escalated", at: r.ended_at ?? r.started_at, title: r.title, detail: r.status === "failed" ? r.error : "Handed to a person", href: `/runs/${r.id}`, tone: r.status === "failed" ? "fail" : "divert", value_usd: null });
    for (const o of r.outcomes)
      items.push({ id: `outcome:${r.id}:${o.type}`, kind: "outcome", at: o.occurred_at, title: o.type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), detail: r.title, href: `/runs/${r.id}`, value_usd: Number(o.value_usd) || null, tone: "clear" });
  }
  return items
    .filter((i) => !before || i.at < before)
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, limit);
}

function search(q: string): S["SearchHit"][] {
  if (!q.trim()) return [];
  const hits: S["SearchHit"][] = [];
  for (const a of approvals.filter((a) => a.status === "pending" && matches(a.description, q)).slice(0, 4))
    hits.push({ kind: "approval", id: a.id, title: a.description, subtitle: `Waiting for ${a.min_role} approval`, href: `/approvals/${a.id}` });
  for (const e of ordered().filter((e) => matches(e.summary.title, q)).slice(0, 4))
    hits.push({ kind: "run", id: e.summary.id, title: e.summary.title, subtitle: e.summary.status.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), href: `/runs/${e.summary.id}` });
  for (const a of (lists["/api/agents"] as S["AgentOut"][]).filter((a) => matches(a.name, q)).slice(0, 4))
    hits.push({ kind: "agent", id: a.id, title: a.name, subtitle: `${a.role} agent`, href: "/agents" });
  for (const w of (lists["/api/workflows"] as S["WorkflowOut"][]).filter((w) => matches(w.name, q)).slice(0, 4))
    hits.push({ kind: "workflow", id: w.id, title: w.name, subtitle: `Runs on ${w.trigger_event}`, href: `/workflows/${w.id}` });
  return hits;
}

// ---- the router -----------------------------------------------------------------------------------

const ACCOUNTS: Record<string, Role> = {
  "owner@northwind.test": "owner",
  "admin@northwind.test": "admin",
  "operator@northwind.test": "operator",
  "viewer@northwind.test": "viewer",
};

function need(role: Role) {
  if (!session || rank(session.role) < rank(role)) throw new DemoError(403, `this needs the ${role} role or higher`);
}

export async function demoRequest(method: string, path: string, query: Query = {}, body: unknown = undefined): Promise<unknown> {
  await new Promise((r) => setTimeout(r, 80 + Math.random() * 120)); // the feel of a network, not the wait
  const b = (body ?? {}) as Record<string, unknown>;
  let m: RegExpMatchArray | null;

  if (method === "POST" && path === "/api/auth/login") {
    const email = String(b.email ?? "").toLowerCase();
    const role = ACCOUNTS[email];
    if (!role) throw new DemoError(401, "Use one of the demo accounts listed on this page.");
    session = { email, role, userId: role === "owner" ? data.user.id : uuid() };
    const name = role === "owner" ? data.user.name : `${role.charAt(0).toUpperCase()}${role.slice(1)} (demo)`;
    return { access_token: "demo", token_type: "bearer", user: { ...data.user, id: session.userId, email, name }, memberships: [{ ...data.tenant, role }] };
  }
  if (!session) {
    // A reload keeps the stored session; recover the role from it.
    try {
      const saved = JSON.parse(localStorage.getItem("oryn.session") ?? "null");
      const role = (saved?.memberships?.[0]?.role as Role) ?? "owner";
      session = { email: saved?.user?.email ?? "owner@northwind.test", role, userId: saved?.user?.id ?? data.user.id };
    } catch {
      session = { email: "owner@northwind.test", role: "owner", userId: data.user.id };
    }
  }

  if (method === "GET") {
    if (path === "/api/runs") {
      let list = ordered().map((e) => e.summary);
      if (query.status) list = list.filter((r) => r.status === query.status);
      if (query.q) list = list.filter((r) => matches(r.title, query.q));
      if (query.before) list = list.filter((r) => r.started_at < String(query.before));
      const limit = Number(query.limit ?? 50);
      const items = list.slice(0, limit);
      return { items, next_cursor: list.length > limit ? items[items.length - 1].started_at : null };
    }
    if (path === "/api/runs/counts") {
      const list = ordered().filter((e) => matches(e.summary.title, query.q));
      const counts: Record<string, number> = { all: list.length };
      for (const s of ["running", "waiting_approval", "completed", "failed", "escalated", "cancelled"]) counts[s] = list.filter((e) => e.summary.status === s).length;
      return counts;
    }
    if ((m = path.match(/^\/api\/runs\/([^/]+)$/))) {
      const e = runs.get(m[1]);
      if (!e) throw new DemoError(404, "run not found");
      return { ...e.detail, route: e.summary.route };
    }
    if ((m = path.match(/^\/api\/runs\/([^/]+)\/spans$/))) return runs.get(m[1])?.spans ?? [];
    if (path === "/api/approvals") return query.status ? approvals.filter((a) => a.status === query.status) : approvals;
    if (path === "/api/activity") return activity(Number(query.limit ?? 30), query.before ? String(query.before) : undefined);
    if (path === "/api/search") return search(String(query.q ?? ""));
    if (path === "/api/simulate/traffic") return traffic;
    if (path === "/api/system/status")
      return {
        ok: true,
        llm_provider: "replay",
        checked_at: now(),
        checks: ["Database", "Redis", "Temporal", "Workers"].map((name) => ({ name, ok: true, latency_ms: 1 + Math.random() * 3, detail: "Simulated in your browser (hosted demo)" })),
      };
    if (path === "/api/metrics/overview") {
      const o = data.get[`/api/metrics/overview?range=${query.range ?? 30}`] as S["OverviewMetrics"];
      const live = ordered().filter((e) => e.summary.status === "running" || e.summary.status === "waiting_approval").length;
      return { ...o, approvals_pending: approvals.filter((a) => a.status === "pending").length, in_flight: live };
    }
    if (path.startsWith("/api/metrics/")) return data.get[`${path}?range=${query.range ?? 30}`] ?? [];
    if (lists[path]) return lists[path];
    if (data.get[path] !== undefined) return data.get[path];
    throw new DemoError(404, "Not available in the hosted demo. Run Oryn OS locally for the full system.");
  }

  if (method === "POST") {
    if ((m = path.match(/^\/api\/approvals\/([^/]+)\/decision$/))) {
      const a = approvals.find((x) => x.id === m![1]);
      if (!a) throw new DemoError(404, "approval not found");
      if (rank(session.role) < rank(a.min_role)) throw new DemoError(403, `this approval requires role ${a.min_role} or higher`);
      if (a.status !== "pending") throw new DemoError(409, `already ${a.status}`);
      Object.assign(a, { status: b.approved ? "approved" : "rejected", decided_at: now(), decided_by: session.userId, comment: (b.comment as string) ?? null });
      emit("approval.decided", a.run_id);
      const e = runs.get(a.run_id);
      const resume = resumeAfter.get(a.id);
      resumeAfter.delete(a.id);
      if (resume) resume(!!b.approved);
      else if (e && e.detail.status === "waiting_approval") continueRecorded(e, !!b.approved);
      if (e) sync(e);
      return a;
    }
    if (path === "/api/simulate/events") {
      need("operator");
      const ids = fire(String(b.type), (b.payload as Record<string, unknown>) ?? {});
      return { event_id: uuid(), created: true, run_ids: ids };
    }
    if (path === "/api/simulate/traffic") {
      need("operator");
      traffic = { enabled: !!b.enabled, rate_per_min: Number(b.rate_per_min ?? 4) };
      scheduleTraffic();
      return traffic;
    }
    if ((m = path.match(/^\/api\/runs\/([^/]+)\/rerun$/))) {
      need("operator");
      const e = runs.get(m[1]);
      if (!e || !e.summary.rerunnable) throw new DemoError(422, "this run has no triggering event to replay");
      const t = template(e.summary.workflow_id, e.detail.approvals.length > 0) ?? e;
      return { event_id: uuid(), created: true, run_ids: [startFrom(t, e.summary.title, e.summary.workflow_id)] };
    }
    if ((m = path.match(/^\/api\/runs\/([^/]+)\/cancel$/))) {
      need("operator");
      const e = runs.get(m[1]);
      if (e) {
        e.detail.status = "cancelled";
        e.detail.ended_at = now();
        sync(e);
        emit("run.updated", e.detail.id);
      }
      return { status: "cancel_requested" };
    }
    if (path === "/api/workflows/draft") {
      const hit = data.drafts[String(b.text ?? "")];
      if (hit) return hit;
      throw new DemoError(422, "The hosted demo knows the example prompts. Run Oryn OS locally to compile your own.");
    }
    if ((m = path.match(/^\/api\/chat\/[^/]+\/sessions$/))) return { session_id: uuid() };
    if (/^\/api\/chat\/[^/]+\/sessions\/[^/]+\/messages$/.test(path)) return data.chat;
    if (path === "/api/api-keys") {
      need("owner");
      const key = { id: uuid(), name: String(b.name ?? "Key"), prefix: "oryn_demo", created_at: now(), last_used_at: null, revoked_at: null };
      lists["/api/api-keys"] = [key, ...lists["/api/api-keys"]];
      return { ...key, key: `oryn_demo_${uuid().replace(/-/g, "")}` };
    }
    if (path === "/api/members") {
      need("owner");
      const mem = { user_id: uuid(), email: String(b.email), name: String(b.name), role: String(b.role ?? "viewer") };
      lists["/api/members"] = [...lists["/api/members"], mem];
      return mem;
    }
    throw new DemoError(403, "Saving this needs the full system. Run Oryn OS locally with make up.");
  }

  if (method === "PATCH") {
    need("admin");
    const kind = path.match(/^\/api\/(agents|workflows|connectors|members)\/([^/]+)$/);
    if (kind) {
      const list = lists[`/api/${kind[1]}`] as Record<string, unknown>[];
      const item = list.find((x) => x.id === kind[2] || x.user_id === kind[2]);
      if (item) Object.assign(item, b, { updated_at: now() });
      return item ?? {};
    }
  }
  if (method === "DELETE") {
    need("admin");
    for (const k of ["/api/api-keys", "/api/memories"]) {
      const id = path.split("/").pop();
      if (path.startsWith(k)) lists[k] = lists[k].filter((x) => (x as { id: string }).id !== id);
    }
    return undefined;
  }
  throw new DemoError(405, "Not available in the hosted demo.");
}
