// Records a snapshot of a running Oryn OS stack for demo mode (the hosted, backend-free build).
//
//   node scripts/record-demo.mjs [api base, default http://localhost:8800]
//
// It signs in with the local demo accounts, starts one fresh lead so there is a decision waiting,
// then saves every response the dashboard reads to src/demo/snapshot.json.
import { writeFileSync } from "node:fs";

const BASE = process.argv[2] ?? "http://localhost:8800";
const PASSWORD = "oryn-demo"; // the seeded local-only demo password
const OUT = new URL("../src/demo/snapshot.json", import.meta.url);

async function login(email) {
  const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: PASSWORD }) });
  if (!r.ok) throw new Error(`login ${email}: ${r.status}`);
  return r.json();
}

function client(session, tenantId) {
  const headers = { Authorization: `Bearer ${session.access_token}`, "X-Tenant-Id": tenantId, Accept: "application/json" };
  return {
    get: async (path, query = {}) => {
      const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== "")).toString();
      const r = await fetch(`${BASE}${path}${qs ? `?${qs}` : ""}`, { headers });
      if (!r.ok) throw new Error(`GET ${path}: ${r.status} ${await r.text()}`);
      return r.json();
    },
    post: async (path, body = {}) => {
      const r = await fetch(`${BASE}${path}`, { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(`POST ${path}: ${r.status} ${await r.text()}`);
      return r.status === 204 ? null : r.json();
    },
  };
}

const owner = await login("owner@northwind.test");
const tenant = owner.memberships.find((m) => m.slug === "northwind") ?? owner.memberships[0];
const api = client(owner, tenant.tenant_id);

// A fresh lead from the operator, so the owner (who didn't start it) can approve it in the demo.
const operator = await login("operator@northwind.test");
await client(operator, tenant.tenant_id).post("/api/simulate/events", {
  type: "lead.created",
  payload: { name: "Maya Chen", email: `maya.${Date.now()}@example.com`, phone: "+15550199", company: "Chen Dental", need: "rooftop unit replacement", budget_usd: 14800, requested_discount_pct: 15, source: "web" },
});
for (let i = 0; i < 40; i++) {
  const waiting = await api.get("/api/approvals", { status: "pending" });
  if (waiting.some((a) => (a.run_title ?? "").includes("Maya Chen"))) break;
  await new Promise((r) => setTimeout(r, 500));
}

const snap = { capturedAt: new Date().toISOString(), tenant, user: owner.user, get: {}, runs: {}, drafts: {}, chat: null };
const keep = (key, value) => (snap.get[key] = value);

for (const range of [7, 30, 90]) {
  keep(`/api/metrics/overview?range=${range}`, await api.get("/api/metrics/overview", { range }));
  keep(`/api/metrics/timeseries?range=${range}`, await api.get("/api/metrics/timeseries", { range }));
  keep(`/api/metrics/agents?range=${range}`, await api.get("/api/metrics/agents", { range }));
}

const runs = [];
let before;
while (runs.length < 140) {
  const page = await api.get("/api/runs", { limit: 100, before });
  runs.push(...page.items);
  if (!page.next_cursor) break;
  before = page.next_cursor;
}
for (const r of runs) {
  snap.runs[r.id] = { summary: r, detail: await api.get(`/api/runs/${r.id}`), spans: await api.get(`/api/runs/${r.id}/spans`) };
}

keep("/api/approvals", await api.get("/api/approvals"));
for (const p of ["/api/agents", "/api/tools", "/api/workflows", "/api/workflows/examples", "/api/connectors", "/api/members", "/api/api-keys", "/api/simulate/traffic"]) keep(p, await api.get(p));
keep("/api/audit", await api.get("/api/audit", { limit: 50 }));
keep("/api/memories", await api.get("/api/memories", { limit: 100 }));
for (const w of snap.get["/api/workflows"]) keep(`/api/workflows/${w.id}`, await api.get(`/api/workflows/${w.id}`));
for (const tab of ["contacts", "deals", "calendar", "messages", "invoices", "tickets", "documents"]) keep(`/api/sandbox/${tab}`, await api.get(`/api/sandbox/${tab}`, { limit: 50 }));
for (const text of snap.get["/api/workflows/examples"]) snap.drafts[text] = await api.post("/api/workflows/draft", { text });

// One real website chat exchange, replayed for any message in the demo.
const session = await api.post(`/api/chat/${tenant.slug}/sessions`);
snap.chat = await api.post(`/api/chat/${tenant.slug}/sessions/${session.session_id}/messages`, { text: "Hi, I'd like to book an appointment" });

writeFileSync(OUT, JSON.stringify(snap));
console.log(`recorded ${runs.length} runs, ${Object.keys(snap.get).length} responses -> ${OUT.pathname}`);
