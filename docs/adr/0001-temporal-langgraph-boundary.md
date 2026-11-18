# ADR 0001: Temporal owns durability; LangGraph owns one agent step

**Status:** accepted

## Context
Both Temporal and LangGraph can orchestrate multi-step processes. An agent platform needs two different
kinds of orchestration: *durable* (survive crashes and deploys, wait days for a human, retry with
backoff, guarantee a side effect happens once) and *cognitive* (an LLM choosing tools in a loop).

## Decision
Temporal workflows own everything durable: the sequence of steps, waits, approvals, retries, handoffs
between agents and compensation. Each agent step is one Temporal activity that runs a LangGraph graph
(think → act) to completion or to a pause point (pending approval, handoff, escalation). The graph's
state is persisted in `agent_threads` so a paused step resumes where it left off.

## Consequences
- Workflow code stays deterministic and replayable; all I/O (LLM calls included) lives in activities.
- A step's retry is a clean redo from a rolled-back transaction, and idempotency keys keep side effects
  exactly-once across retries.
- An LLM loop never holds a durable wait: approvals pause the step and are awaited by the workflow.
- We give up LangGraph's own checkpointer and human-in-the-loop interrupts; Temporal provides stronger
  versions of both.
