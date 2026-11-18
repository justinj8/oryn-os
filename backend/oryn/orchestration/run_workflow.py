"""OrynRunWorkflow — the central orchestrator.

It interprets a pinned workflow definition step by step. Temporal makes every line here
durable: if the worker dies mid-run, a new worker replays the history and continues from
exactly where it stopped. That's why this file contains no I/O — only activities, timers,
signals and pure functions (condition evaluation, escalation decisions).
"""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from oryn.agents.state import ActionOutcome, AgentStepInput, AgentStepOutput, ExecutedAction
    from oryn.core.tenancy import Role
    from oryn.models import AgentRole, MemoryScope, OutcomeType, RunStatus
    from oryn.orchestration.activities import OrynActivities
    from oryn.orchestration.approval_loop import ApprovalLoopCtx, run_approval_loop
    from oryn.orchestration.models import (
        ApprovalDecisionSignal,
        CompensateInput,
        ExecuteActionInput,
        FinalizeInput,
        MarkRunInput,
        NotifyInput,
        OutcomeInput,
        RunInput,
        RunResult,
        RunState,
        SpanEventInput,
    )
    from oryn.orchestration.retry import (
        ACTION_RETRY,
        ACTION_START_TO_CLOSE,
        AGENT_RETRY,
        AGENT_START_TO_CLOSE,
        HEARTBEAT,
        QUICK_RETRY,
        QUICK_START_TO_CLOSE,
    )
    from oryn.workflows.conditions import evaluate
    from oryn.workflows.dsl import (
        END,
        AgentStep,
        ApprovalStep,
        ConditionStep,
        NotifyStep,
        ParallelStep,
        WaitStep,
    )

MAX_HANDOFF_DEPTH = 3


class _Stop(Exception):
    """Ends the run early with a given status (escalation, cancellation)."""

    def __init__(self, status: RunStatus, summary: str) -> None:
        super().__init__(summary)
        self.status, self.summary = status, summary


@workflow.defn(name="OrynRunWorkflow")
class OrynRunWorkflow:
    def __init__(self) -> None:
        self.status = RunStatus.running
        self.current_step: str | None = None
        self.blackboard: dict[str, Any] = {}
        self.pending_approval_id = None
        self.decisions: dict[Any, ApprovalDecisionSignal] = {}
        self.steps_done: list[str] = []
        self.executed: list[ExecutedAction] = []
        self.outcomes: list[OutcomeType] = []
        self.summaries: list[str] = []
        self.cancel_requested = False
        self.inp: RunInput | None = None

    # ------------------------------------------------------------------ signals & queries
    @workflow.signal
    def decide_approval(self, sig: ApprovalDecisionSignal) -> None:
        # Only the approval we're currently waiting on can be decided, and only once.
        if sig.approval_id != self.pending_approval_id or sig.approval_id in self.decisions:
            workflow.logger.info("ignoring stale/duplicate approval decision %s", sig.approval_id)
            return
        self.decisions[sig.approval_id] = sig

    @workflow.signal
    def cancel(self) -> None:
        self.cancel_requested = True

    @workflow.query
    def get_state(self) -> RunState:
        return RunState(
            status=self.status,
            current_step=self.current_step,
            blackboard=self.blackboard,
            pending_approval_id=self.pending_approval_id,
            steps_done=self.steps_done,
        )

    # ------------------------------------------------------------------ helpers
    @property
    def _base(self) -> dict[str, Any]:
        assert self.inp
        return {
            "tenant_id": self.inp.tenant_id,
            "run_id": self.inp.run_id,
            "time_offset_seconds": self.inp.time_offset_seconds,
        }

    async def _quick(self, fn, arg) -> Any:
        return await workflow.execute_activity_method(
            fn, arg, start_to_close_timeout=QUICK_START_TO_CLOSE, retry_policy=QUICK_RETRY
        )

    async def _span(self, kind: str, name: str, data: dict | None = None, status: str = "ok") -> None:
        await self._quick(
            OrynActivities.record_span_event,
            SpanEventInput(**self._base, kind=kind, name=name, data=data or {}, status=status),
        )

    def _set_pending(self, approval_id) -> None:
        self.pending_approval_id = approval_id
        self.status = RunStatus.waiting_approval if approval_id else RunStatus.running

    def _approval_ctx(self) -> ApprovalLoopCtx:
        assert self.inp
        return ApprovalLoopCtx(
            tenant_id=self.inp.tenant_id,
            run_id=self.inp.run_id,
            time_offset_seconds=self.inp.time_offset_seconds,
            time_scale=self.inp.time_scale,
            escalation=self.inp.definition.policies.escalation,
            decision=lambda aid: self.decisions.get(aid),
            set_pending=self._set_pending,
            cancelled=lambda: self.cancel_requested,
        )

    def _subjects(self) -> list[tuple[MemoryScope, str]]:
        assert self.inp
        email = self.inp.trigger.get("email") or self.blackboard.get("contact_email")
        phone = self.inp.trigger.get("phone") or self.blackboard.get("contact_phone")
        keys = []
        if email:
            keys.append((MemoryScope.contact, f"contact:{str(email).lower()}"))
        if phone:
            keys.append((MemoryScope.contact, f"contact:{phone}"))
        return keys

    # ------------------------------------------------------------------ agent steps
    async def _agent(self, role: AgentRole, goal: str, step_key: str, depth: int = 0) -> None:
        assert self.inp
        resume: ActionOutcome | None = None
        while True:
            if self.cancel_requested:
                raise _Stop(RunStatus.cancelled, "Run cancelled.")
            out: AgentStepOutput = await workflow.execute_activity_method(
                OrynActivities.run_agent_step,
                AgentStepInput(
                    tenant_id=self.inp.tenant_id,
                    run_id=self.inp.run_id,
                    step_key=step_key,
                    agent_role=role,
                    goal=goal,
                    blackboard=self.blackboard,
                    trigger=self.inp.trigger,
                    subject_keys=self._subjects(),
                    policies=self.inp.definition.policies.approval,
                    resume_with=resume,
                    time_offset_seconds=self.inp.time_offset_seconds,
                ),
                start_to_close_timeout=AGENT_START_TO_CLOSE,
                heartbeat_timeout=HEARTBEAT,
                retry_policy=AGENT_RETRY,
            )
            self.blackboard.update(out.blackboard_updates)
            self.executed += out.executed_actions

            if out.status == "pending_action":
                p = out.pending_action
                assert p is not None
                decision = await run_approval_loop(
                    self._approval_ctx(),
                    step_id=step_key,
                    tool=p.tool,
                    args=p.args,
                    idempotency_key=p.idempotency_key,
                    description=_describe(p.tool, p.args),
                    reasons=p.requirement.reasons,
                    min_role=p.requirement.min_role,
                    agent_id=p.agent_id,
                )
                if decision.cancelled:
                    raise _Stop(RunStatus.cancelled, "Run cancelled while waiting for approval.")
                if decision.approved:
                    result = await workflow.execute_activity_method(
                        OrynActivities.execute_action,
                        ExecuteActionInput(
                            **self._base,
                            agent_id=p.agent_id,
                            tool=p.tool,
                            args=p.args,
                            idempotency_key=p.idempotency_key,
                        ),
                        start_to_close_timeout=ACTION_START_TO_CLOSE,
                        retry_policy=ACTION_RETRY,
                    )
                    self.executed.append(ExecutedAction(tool=p.tool, idempotency_key=p.idempotency_key, result=result))
                    resume = ActionOutcome(approved=True, result=result, tool_call_id=p.tool_call_id)
                else:
                    resume = ActionOutcome(approved=False, comment=decision.comment, tool_call_id=p.tool_call_id)
                continue

            if out.status == "finished":
                self.summaries.append(out.summary)
                if out.outcome:
                    self.outcomes.append(out.outcome)
                    await self._quick(
                        OrynActivities.record_outcome,
                        OutcomeInput(**self._base, type=out.outcome, value_usd=out.outcome_value_usd or 0),
                    )
                return

            if out.status == "handoff":
                h = out.handoff
                assert h is not None
                self.summaries.append(out.summary)
                if depth + 1 > MAX_HANDOFF_DEPTH:
                    raise _Stop(
                        RunStatus.escalated,
                        f"Escalated: handoff depth exceeded {MAX_HANDOFF_DEPTH} ({role.value} → {h.role.value})",
                    )
                await self._span("handoff", f"{role.value} → {h.role.value}", {"goal": h.goal, "context": h.context})
                await self._agent(h.role, h.goal, f"{step_key}.h{depth + 1}", depth + 1)
                return

            raise _Stop(RunStatus.escalated if out.status == "escalated" else RunStatus.failed, out.summary)

    # ------------------------------------------------------------------ main
    @workflow.run
    async def run(self, inp: RunInput) -> RunResult:
        self.inp = inp
        d = inp.definition
        current = d.first
        status, error = RunStatus.completed, None
        try:
            while current != END:
                if self.cancel_requested:
                    raise _Stop(RunStatus.cancelled, "Run cancelled.")
                step = d.step(current)
                self.current_step = step.id
                await self._quick(
                    OrynActivities.mark_run, MarkRunInput(**self._base, status=RunStatus.running, current_step=step.id)
                )
                if isinstance(step, AgentStep):
                    await self._agent(step.role, step.goal, step.id)
                elif isinstance(step, ConditionStep):
                    taken = evaluate(step.if_, {"trigger": inp.trigger, "blackboard": self.blackboard})
                    nxt = step.then if taken else step.else_
                    await self._span("decision", f"{step.id}: {step.if_} → {nxt}", {"result": taken})
                    self.steps_done.append(step.id)
                    current = nxt
                    continue
                elif isinstance(step, ApprovalStep):
                    r = await run_approval_loop(
                        self._approval_ctx(),
                        step_id=step.id,
                        tool=None,
                        args={},
                        idempotency_key=f"{inp.run_id}:{step.id}:gate",
                        description=step.description,
                        reasons=["workflow requires approval"],
                        min_role=step.min_role,
                    )
                    if r.cancelled:
                        raise _Stop(RunStatus.cancelled, "Run cancelled while waiting for approval.")
                    if not r.approved:
                        self.summaries.append(
                            f"Stopped: '{step.description}' was not approved"
                            f"{' (' + r.comment + ')' if r.comment else ''}."
                        )
                        break
                elif isinstance(step, WaitStep):
                    await self._span("wait", f"wait {step.seconds}s", {"seconds": step.seconds})
                    await workflow.sleep(timedelta(seconds=max(1.0, step.seconds / inp.time_scale)))
                elif isinstance(step, NotifyStep):
                    await self._quick(
                        OrynActivities.send_notification,
                        NotifyInput(**self._base, step=step, trigger=inp.trigger, blackboard=self.blackboard),
                    )
                elif isinstance(step, ParallelStep):
                    await asyncio.gather(*(self._agent(b.role, b.goal, f"{step.id}.{b.id}") for b in step.branches))
                self.steps_done.append(step.id)
                current = d.next_of(step.id)
        except _Stop as stop:
            status = stop.status
            self.summaries.append(stop.summary)
        except ActivityError as e:
            status = RunStatus.failed
            cause = e.cause
            error = cause.message if isinstance(cause, ApplicationError) else str(cause or e)
            self.summaries.append(f"Failed at step '{self.current_step}': {error}")
        if status in (RunStatus.failed, RunStatus.cancelled) and self.executed:
            await self._quick(OrynActivities.compensate, CompensateInput(**self._base, actions=self.executed))
        self.status = status
        summary = " ".join(self.summaries) or "Completed."
        await self._quick(
            OrynActivities.finalize_run,
            FinalizeInput(**self._base, status=status, summary=summary, error=error, blackboard=self.blackboard),
        )
        return RunResult(status=status, summary=summary, outcomes=self.outcomes)


def _describe(tool: str, args: dict[str, Any]) -> str:
    if tool == "crm.apply_discount":
        return f"Apply a {args.get('discount_pct')}% discount"
    if tool == "billing.issue_refund":
        return f"Refund ${float(args.get('amount_usd', 0)):,.2f}"
    return f"{tool} ({', '.join(f'{k}={v}' for k, v in list(args.items())[:3])})"


__all__ = ["MAX_HANDOFF_DEPTH", "OrynRunWorkflow", "Role"]
