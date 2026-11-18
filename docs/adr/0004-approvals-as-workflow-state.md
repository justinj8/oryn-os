# ADR 0004: Approvals are durable workflow state, and actions run outside the agent loop

**Status:** accepted

## Context
Sensitive actions (discounts, refunds, large amounts) need a human. Approvals can take minutes or days,
must survive restarts, must happen exactly once, and the action must not run if declined.

## Decision
- The agent loop never executes an action that needs approval. It returns a `PendingAction` (tool,
  arguments, idempotency key, required role, reasons).
- The workflow records the approval and waits with `wait_condition` and a timeout; humans decide through
  the API, which flips the row from `pending` with a compare-and-set and then signals the workflow.
- Timeouts walk an escalation ladder (`next_escalation`, a pure function safe for workflow code), then
  auto-reject.
- Approved actions run in a separate `execute_action` activity with the original idempotency key, and the
  agent resumes with the result (or with "declined").

## Consequences
- Double clicks, two managers and late decisions are harmless: one decision wins (409 for the rest) and
  stale signals are ignored.
- The same loop serves workflow runs, conversations (which reply "checking with a manager" immediately)
  and MCP calls.
- Auto-reject is the safe default: a stalled approval means the work continues without the risky action.
