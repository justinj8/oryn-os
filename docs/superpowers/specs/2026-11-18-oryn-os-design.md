# Oryn OS — Enterprise AI Agent Operating System

**Design doc · 2026-11-18 · Status: approved 2026-11-18**

> **Oryn OS** — an operating system for your AI workforce.

## 1. Intent

A production-style, multi-tenant platform where a business connects its operational
systems (CRM, email, phone/SMS, calendar, billing, documents, internal databases) and
deploys specialized AI agents that execute real workflows end to end. A central
orchestrator coordinates agents, keeps durable task state, routes work between systems,
retries and recovers from failures, and pauses for human approval on sensitive actions.
A dashboard shows activity, execution traces, cost, completion rates and business impact.

**Why:** a portfolio/resume project. It must prove the system *can be built* — anyone who
clones the repo should see it working in one command, with no API keys and no live
service. Real providers exist and switch on by environment variable, but the offline
path is the primary experience.

## 2. Goals

1. `git clone && make up` (wraps `docker compose up`) → a working platform on
   `localhost` with two seeded tenants, two weeks of historical activity, and live
   simulated traffic. **No keys required.**
2. One **golden path** that is fully real (only the outside world is simulated):
   inbound lead → Sales agent qualifies → hands off to Scheduler agent → books a meeting
   → a discount over threshold triggers **human approval** → CRM updated → follow-up
   email sent → dashboard shows cost, duration and $ impact.
3. Every feature listed in the brief exists and is demonstrable:
   multi-agent delegation + persistent memory; voice/email/chat/API agents; natural-language
   workflow builder; CRM/calendar/billing/database integrations; event-driven orchestration
   with retries and recovery; tenant isolation, RBAC, approval controls; central dashboard.
4. Engineering a reviewer can verify: tests (including Temporal workflow tests and a
   cross-tenant isolation test), CI, typed code, ADRs, an architecture diagram.
5. A **chaos demo**: kill the worker mid-run, restart it, and watch the run resume from
   where it stopped.

## 3. Non-goals

- Running as a hosted SaaS (no deploy target, billing for Oryn OS itself, signup flow, SSO).
- Real OAuth connector setup flows for HubSpot/Google/Stripe (sandbox + adapter interface only).
- A general-purpose visual drag-and-drop workflow editor (the NL builder + a read-only
  graph view cover it).
- Horizontal scale testing / k8s manifests.

## 4. Anti-goals (would make this a failure even if it "works")

- Requires an API key, a Twilio number or an internet connection to see anything.
- Breadth over depth: many integrations that are stubs returning `"ok"`.
- Fake dashboards — every number on the dashboard must come from real rows written by
  real runs (historical seed data is produced by *running* workflows in fast-forward,
  not by inserting fabricated metrics).
- Offline mode that bypasses the real code path. The deterministic LLM must drive the
  *same* LangGraph loop, tool registry, approval policy and Temporal workflow as the
  real LLM.
- Tenant isolation done only in application code.

## 5. Constraints

- Local toolchain: Python 3.13 (containers pin 3.12), Node 24, Docker, uv, pnpm.
- Must run on a laptop: target ≤ 4 GB RAM for the compose stack.
- Stack (given): Python, TypeScript, LangGraph, Temporal, FastAPI, PostgreSQL, Redis,
  Docker, React, Twilio, MCP.

## 6. Approaches considered

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | **Suggested stack, each tool where it's strongest**: Temporal owns durability (workflow state, retries, timers, human-approval waits, crash recovery); LangGraph owns each agent's reasoning loop *inside a single Temporal activity*; Postgres RLS for isolation; Redis for live events | Heavier compose stack (~8 containers); two orchestration layers to explain | **Chosen.** Every resume bullet is real, and the Temporal/LangGraph boundary is a strong interview story |
| B | Home-grown durable job engine on Postgres (job table + outbox), no Temporal | Lighter; but re-implements retries/timers and loses the recognizable durable-execution signal | Rejected |
| C | Microservice per agent with a message bus | Diagram looks impressive; mostly deployment busywork invisible to a reviewer | Rejected |

Picked by: Claude (user delegated the "how").

## 7. Architecture

```
                ┌────────────── React dashboard (Vite/TS) ──────────────┐
                │ Overview · Runs/Traces · Approvals · Agents · Workflows │
                │ Connectors · Channels sim (chat/phone/email) · Settings │
                └──────────────▲───────────────────────┬──────────────────┘
                     SSE (live) │                       │ REST (JWT)
┌────────────┐  webhooks  ┌─────┴───────────────────────▼─────┐      ┌──────────┐
│ Twilio /   ├──────────► │            FastAPI (api)           │◄────►│ Postgres │
│ simulators │            │ auth·RBAC·tenancy·events·builder   │      │ +pgvector│
└────────────┘            └─────┬───────────────▲──────────────┘      │  + RLS   │
                  start/signal  │               │ pub/sub             └────▲─────┘
                         ┌──────▼──────┐   ┌────┴───┐                      │
                         │  Temporal   │   │ Redis  │◄──── trace events ───┤
                         │  server+UI  │   └────────┘                      │
                         └──────┬──────┘                                   │
                                │ tasks                                    │
                         ┌──────▼─────────────────────────────────────────┴┐
                         │ Worker: Temporal workflows + activities          │
                         │  └ LangGraph agent loop → LLM provider           │
                         │       (Anthropic | Replay)                       │
                         │  └ Tool registry → Connectors (sandbox | real)   │
                         └──────────────────────────────────────────────────┘
        MCP server (stdio/HTTP) exposes the same tenant-scoped tool registry externally
```

### 7.1 Containers (docker compose)
`postgres` (pgvector/pgvector:pg16; hosts both the app DB and Temporal's DB) ·
`redis` · `temporal` (auto-setup) · `temporal-ui` · `api` · `worker` · `web` (nginx
serving the built React app; Vite dev server in `make dev`) · `mcp` (optional profile).

### 7.2 Repo layout
```
backend/                 uv project, package `oryn`
  oryn/
    core/                config (pydantic-settings), db, security, tenancy, logging
    models/              SQLAlchemy 2.0 models
    api/                 FastAPI routers (auth, tenants, agents, workflows, runs,
                         approvals, connectors, channels, webhooks, metrics, events/SSE)
    orchestration/       Temporal workflows, activities, worker entrypoint, retry policies
    agents/              LangGraph graph, agent roles, prompts, handoff protocol
    llm/                 LLMProvider protocol, AnthropicProvider, ReplayProvider, pricing
    tools/               tool registry, tool specs, risk metadata
    connectors/          base interfaces; sandbox/*; twilio; smtp; postgres_db
    policies/            approval policy, autonomy levels
    memory/              persistent memory store (pgvector), embeddings (real | hashing)
    builder/             NL → workflow DSL (LLM structured output | offline grammar)
    metrics/             aggregation queries, business-impact model
    mcp_server.py        MCP server over the tool registry
  migrations/            Alembic (includes RLS policies)
  tests/
frontend/                Vite + React + TS + TanStack Query + Tailwind + Recharts
deploy/                  docker-compose.yml, temporal dynamic config, nginx.conf
scripts/                 seed.py, traffic_generator.py, chaos.sh
docs/                    architecture.md, adr/, demo script, screenshots
Makefile                 up, down, dev, seed, test, lint, chaos, demo
.github/workflows/ci.yml
```

## 8. Core concepts & data model

All tenant-owned tables carry `tenant_id` and are protected by **Postgres RLS**.

- **tenants**, **users**, **memberships** (`role ∈ owner|admin|operator|viewer`), **api_keys** (hashed)
- **connectors** — `kind ∈ crm|email|sms|voice|calendar|billing|database|docs`,
  `provider ∈ sandbox|twilio|smtp|postgres|…`, config (secrets encrypted with Fernet,
  key from env)
- **agents** — name, role (`sales|support|scheduler|reporting|ops`), channels, model,
  system prompt, allowed tools, **autonomy level** (`suggest|act_with_approval|autonomous`),
  budget caps (max tokens / max $ per run)
- **workflows** + **workflow_versions** — trigger (event type + filter) and a validated
  JSON **workflow DSL** (below); versions are immutable, runs pin a version
- **events** — inbound events with an idempotency key (unique per tenant)
- **runs** — one per workflow execution; Temporal workflow id, status, trigger event,
  timings, total tokens/cost, outcome
- **spans** — the execution trace: `run_id`, `parent_span_id`, `agent_id`,
  `kind ∈ agent|llm_call|tool_call|handoff|approval|decision|retry|error`, input/output
  (redacted JSON), tokens, cost, latency, attempt number
- **approvals** — run, requested action + payload, risk reasons, required role,
  status, decided_by, decided_at, comment, expires_at
- **memories** — `scope ∈ contact|account|agent|tenant`, subject key, content,
  embedding (`vector(384)`), source run, created_at
- **outcomes** — business impact rows: `meeting_booked|deal_created|ticket_resolved|
  invoice_collected|…`, value_usd, minutes_saved
- **audit_log** — every privileged action (who, what, when, before/after)
- **sandbox_*** — the simulated outside world per tenant: contacts, deals, calendar
  events, messages (email/SMS/chat outbox+inbox), invoices, tickets, call transcripts.
  The dashboard can browse these so you can *see* the agents' effects.

### 8.1 Tenant isolation
- App connects as a non-superuser role without `BYPASSRLS`.
- Every request/activity opens a transaction and runs `SET LOCAL app.tenant_id = …`;
  RLS policies `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
- Temporal workflow ids are namespaced `"{tenant_id}:…"`; activities re-establish tenant
  context from their input, never from global state.
- Redis channels and memory retrieval are tenant-scoped.
- A test proves a query under tenant A cannot read tenant B's rows even with a
  hand-written `SELECT *`.

### 8.2 RBAC
| Capability | owner | admin | operator | viewer |
|---|---|---|---|---|
| View dashboard, runs, traces | ✓ | ✓ | ✓ | ✓ |
| Approve/reject actions (within role limit) | ✓ | ✓ | ✓ | |
| Start/cancel runs, use channel simulators | ✓ | ✓ | ✓ | |
| Manage agents, workflows, connectors | ✓ | ✓ | | |
| Manage members, roles, API keys | ✓ | | | |

Approvals can additionally require a minimum role (e.g. refunds > $500 → admin), and a
user cannot approve an action triggered from their own session.

## 9. Agents (LangGraph)

Each agent step runs a LangGraph `StateGraph` inside one Temporal activity:

```
load_context (memory recall + run blackboard)
   → think (LLM call with tool specs)
   → route: tool_call | handoff | request_approval | finish
        tool_call → policy check → execute (low risk) → observe → think
                                 → needs approval → return PendingAction to workflow
        handoff   → return Handoff(target_role, goal, context) to workflow
        finish    → write memories → return result
```

- **Sensitive side effects never happen inside the agent loop if they need approval.**
  The agent returns a `PendingAction`; the *workflow* durably waits for a decision, then
  calls a separate `execute_action` activity with an idempotency key. This is what makes
  approvals survive restarts and days-long waits.
- **Delegation:** an agent can hand off to another role; the orchestrator schedules the
  target agent with a shared **run blackboard** (structured facts accumulated during the
  run). Max delegation depth and per-run budget caps prevent loops.
- **Persistent memory:** at start, recall top-k memories for the contact/account and the
  agent (pgvector cosine similarity); at finish, the agent writes durable facts
  ("prefers mornings", "budget ~$8k"). Visible and deletable in the UI.
- **Seeded roles:** Sales (qualify, quote, create deal), Scheduler (find slots, book,
  reschedule), Support (triage tickets, answer from docs, refund requests), Reporting
  (query internal DB, produce a weekly summary), Ops (invoice follow-ups).

## 10. LLM layer — offline by default

`LLMProvider` protocol: `complete(messages, tools, response_schema?) → LLMResult`
(text, tool_calls, usage).

- **ReplayProvider (default, offline):** deterministic, rule-driven policy per agent role
  that reads the conversation/tool results and emits the same tool calls / handoffs /
  finish messages a real model would. Seeded randomness for variety; token usage is
  estimated from message length and priced with the real price table, flagged
  `simulated=true` in spans and the UI.
- **AnthropicProvider:** enabled when `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`
  are set; uses tool use and structured output; model configurable per agent (defaults to
  the current Claude Sonnet model).
- Same interface → same graph, tools, policies and workflow in both modes.

## 11. Orchestration (Temporal)

- **Ingest:** `POST /webhooks/{tenant}/{source}` (Twilio form payloads, email JSON,
  chat, generic API) → store event (idempotent) → match workflow triggers → start
  `WorkflowRun` with id `{tenant}:{workflow}:{event_id}` (duplicate events are no-ops).
  Redis publishes `event.received`.
- **WorkflowRun** interprets the pinned workflow DSL. Step types:
  `agent` (run an agent with a goal), `approval` (explicit gate), `condition`,
  `parallel`, `wait` (durable timer, e.g. "remind 24h before"), `notify`.
  Dynamic handoffs returned by agents are scheduled as additional `agent` steps.
- **Approvals:** create approval row → notify (SSE + optional SMS) → `wait_condition` for
  `approval_decided` signal with timeout → on timeout, escalate to next role or
  auto-reject per policy.
- **Retries & recovery:** per-activity retry policies (exponential backoff, max attempts),
  connector errors classified `Retryable` vs `NonRetryable`; sandbox connectors support
  fault injection (`SANDBOX_FAILURE_RATE`, `SANDBOX_LATENCY_MS`) so retries show up in
  traces. Non-retryable failures run a compensation step (e.g. release a held calendar
  slot) and mark the run `failed` with a reason. `make chaos` kills the worker mid-run to
  demonstrate replay-based resumption.
- **Queries/signals:** `get_state` query powers the live run view; `cancel` signal.
- **Observability:** every activity writes spans and publishes them to Redis → SSE.

### 11.1 Workflow DSL (JSON, Pydantic-validated)
```json
{
  "name": "Inbound lead to booked meeting",
  "trigger": {"event": "lead.created"},
  "steps": [
    {"id": "qualify", "type": "agent", "role": "sales",
     "goal": "Qualify the lead and propose a quote"},
    {"id": "gate", "type": "condition", "if": "blackboard.qualified == true",
     "then": "book", "else": "nurture"},
    {"id": "book", "type": "agent", "role": "scheduler",
     "goal": "Book a 30-min consult within 5 business days"},
    {"id": "nurture", "type": "notify", "channel": "email", "template": "nurture"}
  ],
  "policies": {"approval": {"discount_pct_over": 10, "refund_usd_over": 200}}
}
```

## 12. Natural-language workflow builder

`POST /workflows/draft {text}` → DSL draft + a rendered graph + validation warnings →
user reviews → saves as a new version.
- **Offline:** a deterministic compiler for a documented phrase grammar ("when X happens",
  "have the sales agent …", "if … then …", "ask a manager before …", "wait 2 days",
  "send an email …"). Unknown phrases become warnings, never silent drops.
- **Online:** Claude structured output against the same JSON schema, then the same
  validator.
- The UI shows example prompts that are guaranteed to compile offline.

## 13. Channels

| Channel | Offline | Real (env-switched) |
|---|---|---|
| Chat | Chat widget in the dashboard + public chat API | same |
| Email | Simulated inbox/outbox in UI; inbound via webhook JSON | SMTP send (`SMTP_URL`) |
| SMS | Phone simulator posts Twilio-shaped form payloads to the real webhook | Twilio Messaging |
| Voice | Phone simulator "call" with text turns → same voice webhook (TwiML `<Gather>`) | Twilio Voice with speech `<Gather>` |
| API | `POST /v1/agents/{id}/invoke` with tenant API key | same |

The simulators exercise the exact production webhook handlers (including Twilio request
signature validation, bypassed only in sandbox mode).

## 14. Integrations

Adapter interfaces: `CRM`, `Calendar`, `Billing`, `Messaging`, `Voice`, `Database`,
`Docs`. Each tool in the registry declares name, JSON schema, connector kind,
**risk level** and whether it is side-effecting.

- **Sandbox implementations for every interface** (stateful, per tenant, in Postgres,
  browsable in UI, with fault injection).
- **Real implementations:** Anthropic (LLM), Twilio (SMS + voice), SMTP (email), and a
  read-only Postgres `Database` connector (runs against a seeded "internal warehouse"
  schema by default, or any DSN you configure). CRM/calendar/billing real providers are
  out of scope; the interfaces are documented so adding HubSpot/Google/Stripe is a single
  class each.
- **MCP:** an MCP server exposes a tenant's tool registry (with the same policy checks)
  so an external MCP client can drive Oryn OS's tools.

## 15. Dashboard (React)

- **Overview:** runs today/7d/30d, completion rate, p50/p95 duration, LLM cost (total, per
  run, per agent), pending approvals, retry/failure rate, and **business impact**:
  meetings booked, pipeline $ created, tickets resolved, hours saved × loaded hourly rate
  vs. AI cost → ROI. Tenant-switcher for users in multiple tenants.
- **Runs:** filterable list; **trace view** = timeline/waterfall of spans with
  inputs/outputs, tokens, cost, retries, handoffs; live updates via SSE.
- **Approvals inbox:** action, payload diff, risk reasons, approve/reject with comment.
- **Agents:** config, autonomy level, budget, tools, memory browser.
- **Workflows:** NL builder, DSL view, rendered graph, versions.
- **Connectors:** status, provider (sandbox/real), fault-injection toggles, sandbox data
  browser (CRM records, calendar, outbox).
- **Simulators:** chat, phone (SMS/voice), email inbox, "fire event" buttons, live
  traffic toggle.
- **Settings:** members, roles, API keys, audit log.

## 16. Seed & demo

- Tenants: **Northwind HVAC** (sales, scheduling, support, billing follow-ups) and
  **Brightsmile Dental** (appointment booking + reminders, support). Different data,
  proving isolation.
- Users per role per tenant with documented demo passwords (local only).
- `scripts/seed.py` runs the real workflows on the real Temporal server against ~2 weeks
  of generated events. Time-skipping only exists in Temporal's test environment, so the
  seed uses an injectable clock (event/run timestamps back-dated to their simulated time)
  and a `DEMO_TIME_SCALE` that shrinks `wait` steps and approval timeouts; seeded approvals
  are decided by a scripted "demo manager" user through the normal signal path.
- The ReplayProvider handles free-form chat/SMS/voice text with keyword intent matching
  and templated replies; anything it cannot classify is escalated to a human (a
  realistic behavior, not a dead end).
- `scripts/traffic_generator.py` (toggle in UI) produces live events.
- `docs/demo.md`: a 5-minute walkthrough script (golden path, approval, chaos restart,
  tenant switch, NL builder).

## 17. Quality

- Backend: ruff, mypy (strict on core packages), pytest. Tests include Temporal workflow
  tests with `WorkflowEnvironment` (time skipping, approval signal, retry, worker
  restart replay), RLS isolation tests against real Postgres, API/RBAC tests, NL compiler
  golden tests, ReplayProvider determinism tests.
- Frontend: tsc, eslint, vitest for key components; a Playwright smoke test of the
  golden path.
- CI: GitHub Actions — lint, type-check, tests (with Postgres/Redis/Temporal service
  containers), docker build.
- Docs: README (what/why, 1-command quickstart, screenshots/GIF, architecture diagram,
  feature → file map for reviewers), `docs/architecture.md`, ADRs (Temporal vs LangGraph
  boundary, RLS, offline Replay LLM, approval-as-workflow-state).

## 18. Build order (each phase ends runnable)

1. Foundation: compose stack, config, DB + migrations + RLS, auth/JWT, RBAC, tenants, seed users.
2. Connectors (sandbox), tool registry, risk metadata.
3. LLM providers (Replay + Anthropic), LangGraph agent loop, memory.
4. Temporal workflows/activities, approvals, retries, events/webhooks, spans + SSE.
5. Channels: chat, email, SMS/voice (Twilio-shaped simulators + real adapters).
6. NL workflow builder.
7. React dashboard.
8. Metrics/impact, seed history, traffic generator, MCP server, chaos script.
9. Tests hardening, CI, README/ADRs/demo doc, screenshots.

## 19. Calls made by Claude (please check)

- Name "Oryn OS" (Python package `oryn`); repo layout `backend/` + `frontend/` + `deploy/`.
- Real providers limited to Anthropic, Twilio, SMTP, Postgres; CRM/calendar/billing are
  sandbox-only behind interfaces (to avoid shipping untested code).
- One Postgres instance hosts both app and Temporal DBs (laptop-friendly).
- Offline embeddings via a deterministic hashing embedder (384-dim) so pgvector recall
  works without a model download; real embeddings are a pluggable provider.
- Seed tenants: Northwind HVAC and Brightsmile Dental.
- Historical dashboard data is produced by actually running workflows, not inserted.
- **Interview-critical decision functions** — written by Claude, then walked through with
  the user (`docs/interview-guide.md`): approval policy (`policies/approval.py`),
  escalation on approval timeout, retry classification for connector errors, and the
  Temporal/LangGraph handoff boundary. Each gets focused tests and a short "why it's
  shaped this way / alternatives considered" write-up.

## 20. Left to the builder

Exact UI styling, chart choices, prompt wording, ReplayProvider rule details, span
redaction rules, specific retry numbers, pagination, error message copy.
