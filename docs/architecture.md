# Architecture

Oryn OS has five moving parts: an **API** (FastAPI), a **worker** (Temporal workflows and activities,
LangGraph agents), **Temporal** (durable execution), **Postgres** (data, row-level security, pgvector
memory) and **Redis** (live events). The React dashboard talks to the API over REST and server-sent
events.

## Components

| Component | Responsibility | Where |
|---|---|---|
| API | Auth (JWT, API keys), tenant context, RBAC, event ingest, channel webhooks, approvals, metrics, SSE | `backend/oryn/api/` |
| Run workflow | Interprets a pinned workflow definition: agent steps, conditions, approval gates, waits, notifications, parallel steps; handoffs; compensation | `backend/oryn/orchestration/run_workflow.py` |
| Conversation workflow | One long-lived workflow per customer conversation; each message is a Temporal Update that returns the reply | `backend/oryn/orchestration/conversation_workflow.py` |
| MCP action workflow | A side-effecting tool call from an external MCP client, held for approval | `backend/oryn/orchestration/mcp_action_workflow.py` |
| Activities | Every side effect: agent steps, approvals, idempotent action execution, notifications, outcomes, compensation | `backend/oryn/orchestration/activities.py` |
| Agent loop | LangGraph state machine (think → act) with approval interception, handoffs, memory, budget and iteration caps | `backend/oryn/agents/graph.py`, `backend/oryn/agents/runner.py` |
| LLM providers | Claude (Anthropic SDK) and the offline Replay provider, same interface | `backend/oryn/llm/` |
| Tool registry | Typed tools with risk level, side-effect flag and money fields | `backend/oryn/tools/` |
| Policies | Approval policy and escalation ladder (pure functions) | `backend/oryn/policies/` |
| Connectors | CRM, Calendar, Billing, Messaging, Database, Docs interfaces; sandbox, Twilio, SMTP implementations | `backend/oryn/connectors/` |
| Workflow DSL | Validated JSON definition and a safe condition language | `backend/oryn/workflows/` |
| Builder | Natural language → workflow definition | `backend/oryn/builder/` |
| Observability | Span recorder, Redis event bus, SSE endpoint | `backend/oryn/observability/`, `backend/oryn/api/routes/events.py` |

## Data model

Global tables: `tenants`, `users`. Everything else carries `tenant_id` and an RLS policy:
`memberships`, `api_keys`, `audit_log`, `connectors`, `agents`, `workflows`, `workflow_versions`
(immutable; runs pin a version), `events` (unique per idempotency key), `runs`, `spans` (the execution
trace), `approvals`, `agent_threads` (an agent step's conversation, so it can resume after approval),
`memories` (pgvector), `outcomes` (business impact), `conversations`, and the sandbox world
(`sb_contacts`, `sb_deals`, `sb_calendar_events`, `sb_messages`, `sb_invoices`, `sb_tickets`,
`sb_documents`, `sb_action_log` for idempotency).

## Key flows

### Event → run
`ingest_event` (`backend/oryn/services/ingest.py`) inserts the event with `ON CONFLICT DO NOTHING` on
`(tenant_id, idempotency_key)`. A duplicate delivery returns the runs the first delivery started. For
each enabled workflow whose trigger and filter match, it creates a `runs` row and, after the commit,
starts `OrynRunWorkflow` with id `{tenant}:{workflow}:{event}` and a reject-duplicate policy, so even a
race can only start one run.

### Agent step
`run_agent_step` opens one tenant-scoped transaction, builds the connector set, and runs the LangGraph
loop. The thread is loaded from `agent_threads`, so a step resumed after an approval continues the same
conversation. Transient tool errors fail the step, and Temporal retries it from a clean transaction;
permanent errors go back to the model as tool results. Spans are written on a separate connection pool
in their own short transactions, so the trace survives even when the step rolls back.

### Approval
When the loop proposes a side-effecting tool, `evaluate_approval` decides. If a human is needed, the step
ends with a `PendingAction`. The workflow calls `run_approval_loop`, which records the approval and waits
on a condition with a timeout. A human decision arrives as a signal, after the API has atomically flipped
the row from `pending`. Timeouts escalate up the role ladder, then auto-reject. Approved actions run in
`execute_action` with the step's idempotency key; the agent then resumes with the outcome.

### Conversation turn
The chat API or a Twilio webhook calls `send_message`, which starts the conversation workflow if needed
(`USE_EXISTING` conflict policy) and sends a Temporal **Update**. The update handler runs one agent turn
and returns the reply synchronously. A pending approval returns a holding reply immediately; the
follow-up is delivered over the channel when the decision comes in.

## Failure handling

| Failure | Behavior |
|---|---|
| Duplicate webhook | Same event row, same runs; Twilio duplicates reuse the conversation's stored reply |
| Transient connector error, rate limit | Step fails and Temporal retries with backoff (rate limits wait longer); a retry span is recorded and the crashed attempt's spans are marked interrupted |
| Permanent connector error | Shown to the model as a tool result; repeated failures escalate to a human |
| Approved action fails permanently | Run fails, executed actions are compensated (bookings cancelled) |
| Worker crash | Temporal replays the workflow on another worker; side effects are idempotent; `scripts/chaos.sh` demonstrates it |
| Agent loops or overspends | 8-iteration cap, per-agent token and dollar budget, handoff depth limit of 3; the run escalates |
| Nobody answers an approval | Escalates operator → admin → owner with doubling timeouts, then auto-rejects |

## Security

- Tenant isolation is enforced by Postgres RLS (`FORCE ROW LEVEL SECURITY`); the runtime role has no
  `BYPASSRLS`. The two legitimate cross-tenant lookups (a user's memberships at login, API key
  resolution) are narrow `SECURITY DEFINER` functions.
- Passwords use argon2; API keys are stored as SHA-256 hashes and shown once.
- Approvals are role-gated, and nobody can approve a run they started.
- Twilio webhooks verify request signatures when an auth token is configured.
- The internal-database tool accepts a single `SELECT`, wrapped in a subquery (which rejects
  data-modifying CTEs), under the tenant's RLS context.
- Connector secrets are stored encrypted and never returned by the API.
