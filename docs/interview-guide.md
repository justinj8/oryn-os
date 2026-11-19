# Interview guide

Prep notes for discussing Oryn OS: the pitch, how a request flows through the system, the decision
functions that carry the design, and the bugs that only showed up when the system ran for real. Every
section points at the code and the tests that pin it, so you can open them during an interview.

## The 60-second pitch

> Oryn OS is a multi-tenant platform for running AI agents that do real operational work: qualify
> leads, book appointments, answer support, chase invoices. The interesting part isn't the agents, it's
> the operating system around them. Every run is a durable Temporal workflow, so a crash or a
> three-day wait for a manager loses nothing. Each agent step is a LangGraph loop inside one Temporal
> activity, and before any risky action runs, a pure policy function decides whether a human must
> approve it and how senior they must be. Side effects are idempotent, tenants are isolated by Postgres
> row-level security, and there's a dashboard showing traces, cost and business impact. It runs offline
> with one command, and I chaos-tested it by killing the worker mid-booking.

## How a request flows end to end

Use the golden path: a lead that asks for a 15% discount.

| Step | What happens | Code |
|---|---|---|
| 1 | Webhook or simulator posts `lead.created` | `backend/oryn/api/routes/webhooks.py` |
| 2 | Event stored idempotently; matching workflows found; `runs` rows committed; `OrynRunWorkflow` started with a deterministic id | `backend/oryn/services/ingest.py:45` |
| 3 | Workflow interprets the pinned definition and schedules the Sales step | `backend/oryn/orchestration/run_workflow.py:67` |
| 4 | Activity opens one tenant-scoped transaction, loads the agent thread, runs LangGraph | `backend/oryn/orchestration/activities.py`, `backend/oryn/agents/runner.py:60` |
| 5 | Sales proposes `crm.apply_discount`; the loop evaluates the approval policy and stops with a `PendingAction` | `backend/oryn/agents/graph.py:171` |
| 6 | Workflow records the approval and waits durably, escalating on timeout | `backend/oryn/orchestration/approval_loop.py:60` |
| 7 | Admin approves; the API flips the row with a compare-and-set, then signals | `backend/oryn/services/approvals.py:44` |
| 8 | `execute_action` applies the discount with the original idempotency key; Sales resumes and hands off | `backend/oryn/orchestration/run_workflow.py` |
| 9 | Scheduler books, emails, reports `meeting_booked`; the explicit scheduler step is skipped because the handoff satisfied it | `backend/oryn/orchestration/run_workflow.py:263` |
| 10 | Every model call, tool call and decision is a span, streamed over Redis and SSE | `backend/oryn/observability/spans.py` |

## The decision functions

### 1. `evaluate_approval`: who has to approve what
`backend/oryn/policies/approval.py:78`, tests in `backend/tests/policies/test_approval.py`.

**What it does.** Given a proposed action, the agent's autonomy level and the workflow's policy, it
returns whether approval is required, the minimum role, and *every* reason.

**Why it's shaped this way.**
- It's **pure**: no I/O, so it's trivially testable and can be explained as a table.
- **Three owners, one decision.** Risk comes from the tool spec (the platform), thresholds from the
  workflow (the business), autonomy from the agent (its admin). None of them can be bypassed by another.
- **Rules accumulate.** Every rule that fires adds a reason and the strictest role wins, so the approver
  sees all the reasons, not just the first.
- **Money fields are declared, not hard-coded.** The tool spec says which argument is an amount or a
  percentage, so a new money-moving tool doesn't mean editing this function.
- It runs **inside the agent loop**, at the moment of proposal, before anything touches the outside world.

**Alternatives considered.** A rules engine or OPA/Rego: more flexible, but overkill for a handful of
rules and harder to explain. LLM self-assessment of risk: not auditable and not deterministic.

**Likely questions.**
- *Why does an 8% discount still need approval if the policy is 10%?* Discounts are high-risk tools, so
  any discount by an autonomous agent needs an operator; the 10% policy adds a second reason and, for
  refunds, a higher role. You'd loosen this by lowering the tool's risk level, which is a deliberate,
  visible change.
- *How would you add "no refunds on weekends"?* Pass the time in through the context (keeping the
  function pure) and add one rule and one test row.

### 2. `next_escalation`: what happens when nobody answers
`backend/oryn/policies/escalation.py:34`, tests in `backend/tests/policies/test_escalation.py`.

**What it does.** On timeout it escalates to the next role up the ladder (operator → admin → owner),
doubling the wait each time, and auto-rejects once the ladder runs out.

**Why it's shaped this way.**
- It's called **from Temporal workflow code**, which must be deterministic so it can be replayed after a
  crash. So it can't read the clock or the database: the workflow passes in the current role and level.
- **Doubling timeouts** interrupt senior people less often.
- **Auto-reject, not auto-approve.** A stalled approval means the agent continues *without* the risky
  action, and the reason is recorded. Failing open would let silence approve a refund.

**Likely question.** *What if a manager approves at the same moment it auto-rejects?* The API's
compare-and-set means exactly one decision wins. If the human's lands first, `update_approval_status`
returns "approved" and the workflow honors it (`backend/oryn/orchestration/approval_loop.py:101`).

### 3. `classify_error`: retry or give up
`backend/oryn/connectors/errors.py:35`, tests in `backend/tests/connectors/test_errors.py`.

**What it does.** Maps any exception to `retryable`, `rate_limited` or `non_retryable`.

**Order of rules and why.**
1. Explicit `RetryableConnectorError` or `NonRetryableConnectorError` wins: the connector author knows best.
2. HTTP semantics: 429 waits longer; 408 and 5xx are transient; other 4xx mean the request is wrong.
3. Timeouts and connection errors are transient.
4. Validation and value errors are permanent.
5. **Unknown errors are retried.** This is safe *because* every side effect carries an idempotency key,
   while giving up on a transient failure would drop real work.

**Where it's used.** In the agent loop, transient errors fail the whole step, so Temporal retries it from
a clean transaction, and permanent errors go back to the model as a tool result so it can choose another
path (`backend/oryn/agents/graph.py:206`). In activities, it maps to Temporal's `ApplicationError` with
`non_retryable` or a longer `next_retry_delay`.

### 4. Approval interception in the agent loop
`backend/oryn/agents/graph.py:164` (`_business_tool`).

**The key design decision in the project:** a side-effecting tool that needs approval is *never executed
inside the agent loop*. The loop returns a `PendingAction`, the activity ends, and the **workflow** waits.

**Why.** An LLM loop is the wrong place for a wait that can last days: activities have timeouts and
heartbeats, and a crash would lose the in-memory state. Temporal workflow state is durable and
replayable. After approval, the action runs in its own idempotent activity, and the agent resumes from
its saved thread with the outcome appended as the tool result (`backend/oryn/agents/runner.py:60`).

### 5. `run_approval_loop`: one durable wait, three callers
`backend/oryn/orchestration/approval_loop.py:60`. Used by the run workflow, the conversation workflow
(which replies "checking with a manager" immediately and follows up later) and the MCP action workflow.

### 6. `tenant_session` and row-level security
`backend/oryn/core/db.py:50`, `backend/migrations/rls.py:8`, tests in
`backend/tests/core/test_rls.py` and `backend/tests/core/test_schema.py`.

Each transaction runs `set_config('app.tenant_id', …, true)`, and every tenant table enforces
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`. The runtime role cannot bypass
RLS. A schema test fails the build if any table with a `tenant_id` column lacks the policy.

**Likely question.** *Why `NULLIF`?* Pooled connections reset a local setting to the empty string, not
`NULL`, and `''::uuid` would raise an error instead of returning no rows.

### 7. Idempotency everywhere
Event ingest (unique key per tenant), workflow ids derived from event ids, action keys of the form
`{run}:{step}:{tool_call_id}` recorded in `sb_action_log`, compare-and-set on approvals, Twilio
`MessageSid` as the conversation message id. The chaos test proves it: kill the worker mid-booking and
there is still exactly one booking.

## Bugs found by running the system

These are good stories because each one passed unit tests and only appeared when the whole system ran.
Each was reproduced by a failing test before it was fixed.

**Connection-pool starvation.** The first 14-day backfill stalled with `QueuePool limit reached`. An agent
step holds a pooled connection for its whole transaction, and its span writes opened a *second*
connection from the same pool so traces survive retries. With about 50 concurrent steps, every connection
was held by a step waiting for one more. Fix: a dedicated pool for trace writes, and worker concurrency
bounded below the step pool. Test: `test_span_writes_do_not_need_the_step_pool`.

**Double booking.** The seeded data had 210 `meeting_booked` outcomes for 144 runs. The natural-language
lead workflow has an explicit scheduler step, *and* the sales agent hands off to the scheduler, so the
scheduler ran twice. Fix: a role that finished via handoff satisfies the next explicit step for that role,
recorded as a visible decision span. Test: `test_handoff_satisfies_the_next_step_for_that_role`.

**An update racing its workflow's start.** On the real Temporal server, a chat's first message can arrive
in the same workflow task as the start, so the update handler ran before `run()` had stored the input. The
time-skipping test server's timing hid it. Fix: `@workflow.init`, so the constructor receives the input
(`backend/oryn/orchestration/conversation_workflow.py:79`). Test:
`test_first_message_delivered_with_workflow_start`, which reproduces it deterministically by queuing the
message before any worker exists.

**Orphaned spans after a crash.** The chaos test's trace showed the interrupted attempt's spans stuck in
"running" forever. Fix: a retried step marks spans left open by earlier attempts as interrupted. Test:
`test_retry_closes_spans_left_open_by_a_crashed_attempt`.

**The demo was slow right when people try it.** On a fresh `make up`, ~300 history-backfill runs filled
the worker's task queue, so anything a person clicked waited minutes behind them; the chaos and
end-to-end checks timed out. Fix: the backfill runs on its own task queue, and the worker polls both
with separate concurrency budgets (16 live, 6 backfill). Live work stays fast while history fills in.

**A scripted manager approving real people's work.** During the backfill, the scripted "demo manager"
approved *every* pending approval in the tenant, including the one a person had just triggered. Fix:
it only decides approvals on runs whose trigger event came from the backfill. Test:
`test_demo_manager_only_decides_backfill_approvals`.

**A lost return, caught by mypy.** `update_approval_status` is documented to return the approval's final
status, but an edit had dropped the final `return`, so it returned `None`. Behavior happened to be right,
but the contract wasn't. Test: `test_update_approval_status_returns_final_status`.

## Trade-offs and what's next

- **Replay model.** Offline runs use scripted per-role behavior; it exercises every code path but doesn't
  reason. The provider interface makes Claude a configuration change.
- **Sandbox integrations.** CRM, calendar and billing are realistic stateful sandboxes behind interfaces.
  Next: HubSpot, Google Calendar and Stripe implementations, with OAuth connection flows.
- **Scale.** One worker process and one database. Next: horizontal workers (Temporal makes this a
  deployment change), partitioning `spans` by time, and moving metrics to rollup tables.
- **Evaluation.** Next: an eval set of recorded conversations to compare prompts and models on
  completion rate, approvals triggered and cost per outcome.
