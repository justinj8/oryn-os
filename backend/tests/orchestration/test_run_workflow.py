import pytest
from sqlalchemy import func, select
from temporalio.client import WorkflowFailureError

from oryn.connectors.errors import NonRetryableConnectorError
from oryn.core.db import owner_session
from oryn.llm.replay.provider import ReplayProvider
from oryn.llm.types import LLMResult, ToolCall, Usage
from oryn.models import (
    Approval,
    Connector,
    ConnectorKind,
    Outcome,
    Run,
    RunStatus,
    SbActionLog,
    SbCalendarEvent,
    SbDeal,
    Span,
    SpanKind,
)
from oryn.orchestration.activities import OrynActivities
from oryn.orchestration.models import ApprovalDecisionSignal
from oryn.orchestration.run_workflow import OrynRunWorkflow
from tests.orchestration.wf_helpers import GOLDEN, start, wait_state, worker


@pytest.fixture
def env(temporal_env):
    return temporal_env


async def _approve(h, approved=True, comment=None):
    st = await wait_state(h, "waiting_approval")
    await h.signal(
        OrynRunWorkflow.decide_approval,
        ApprovalDecisionSignal(approval_id=st.pending_approval_id, approved=approved, comment=comment),
    )
    return st


async def test_golden_path_completes(env, tenant, acts) -> None:
    async with worker(env.client, acts):
        h, rid = await start(env.client, tenant)
        st = await _approve(h)
        assert st.current_step == "qualify"
        res = await h.result()
    assert res.status == RunStatus.completed
    assert "meeting_booked" in res.outcomes
    async with owner_session() as s:
        run = await s.get(Run, rid)
        assert run.status == RunStatus.completed and run.total_cost_usd > 0 and run.blackboard["qualified"] is True
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1
        assert (await s.execute(select(SbDeal.discount_pct))).scalar_one() == 15
        kinds = set((await s.execute(select(Span.kind).where(Span.run_id == rid))).scalars())
        assert {SpanKind.agent, SpanKind.llm_call, SpanKind.tool_call, SpanKind.approval, SpanKind.handoff} <= kinds
        assert (await s.execute(select(Outcome.type))).scalars().all() == ["meeting_booked"]


async def test_rejected_discount_still_books(env, tenant, acts) -> None:
    async with worker(env.client, acts):
        h, _ = await start(env.client, tenant)
        await _approve(h, approved=False, comment="too generous")
        res = await h.result()
    assert res.status == RunStatus.completed
    async with owner_session() as s:
        assert (await s.execute(select(SbDeal.discount_pct))).scalar_one() == 0
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1


async def test_approval_timeout_escalates_then_auto_rejects(isolated_temporal_env, tenant, acts) -> None:
    env = isolated_temporal_env
    async with worker(env.client, acts):
        h, _ = await start(env.client, tenant)
        res = await h.result()  # nobody answers; time-skipping fast-forwards the timers
    assert res.status == RunStatus.completed
    async with owner_session() as s:
        a = (await s.execute(select(Approval))).scalar_one()
        assert a.status == "rejected" and a.escalation_level == 2 and a.min_role == "owner"
        assert a.comment == "no decision after 2 escalations"
        assert (await s.execute(select(SbDeal.discount_pct))).scalar_one() == 0
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1


async def test_transient_failures_are_retried(env, tenant, acts) -> None:
    async with owner_session() as s:
        cal = (await s.execute(select(Connector).where(Connector.kind == ConnectorKind.calendar))).scalar_one()
        cal.settings = {"fail_attempts": 1}  # calendar is down for the first attempt
    async with worker(env.client, acts):
        h, rid = await start(env.client, tenant)
        await _approve(h)
        res = await h.result()
    assert res.status == RunStatus.completed
    async with owner_session() as s:
        retries = (
            await s.execute(
                select(func.count()).select_from(Span).where(Span.run_id == rid, Span.kind == SpanKind.retry)
            )
        ).scalar_one()
        assert retries == 1
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1


class _FailReporting:
    def __init__(self) -> None:
        self.inner = ReplayProvider()

    async def complete(self, **kw) -> LLMResult:
        if kw["context"].agent_role == "reporting":
            raise NonRetryableConnectorError("model rejected the request", provider="test", status_code=400)
        return await self.inner.complete(**kw)


async def test_non_retryable_failure_compensates(env, tenant, acts) -> None:
    acts = OrynActivities(_FailReporting(), acts.memory, acts.bus, acts.registry, acts.settings)
    definition = {
        "name": "x",
        "trigger": {"event": "e"},
        "steps": [
            {"id": "book", "type": "agent", "role": "scheduler", "goal": "Book a consult"},
            {"id": "report", "type": "agent", "role": "reporting", "goal": "Report"},
        ],
    }
    async with worker(env.client, acts):
        h, rid = await start(env.client, tenant, definition)
        res = await h.result()
    assert res.status == RunStatus.failed
    async with owner_session() as s:
        run = await s.get(Run, rid)
        assert run.status == RunStatus.failed and run.error
        assert (await s.execute(select(SbCalendarEvent.status))).scalar_one() == "cancelled"


async def test_approval_signal_after_completion_is_ignored(env, tenant, acts) -> None:
    async with worker(env.client, acts):
        h, _ = await start(env.client, tenant)
        st = await wait_state(h, "waiting_approval")
        sig = ApprovalDecisionSignal(approval_id=st.pending_approval_id, approved=True)
        await h.signal(OrynRunWorkflow.decide_approval, sig)
        await h.signal(OrynRunWorkflow.decide_approval, sig)  # double-click
        await h.result()
    async with owner_session() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(SbActionLog).where(SbActionLog.tool == "crm.apply_discount")
            )
        ).scalar_one()
    assert n == 1


class _PingPong:
    async def complete(self, **kw) -> LLMResult:
        role = kw["context"].agent_role
        target = "scheduler" if role == "sales" else "sales"
        return LLMResult(
            text="",
            tool_calls=[
                ToolCall(
                    id=f"h{len(kw['messages'])}",
                    name="control.handoff",
                    arguments={"role": target, "goal": "you take it"},
                )
            ],
            usage=Usage(input_tokens=5, output_tokens=5),
            model="m",
            simulated=True,
            stop_reason="tool_use",
        )


async def test_handoff_depth_cap(env, tenant, acts) -> None:
    acts = OrynActivities(_PingPong(), acts.memory, acts.bus, acts.registry, acts.settings)
    async with worker(env.client, acts):
        h, _ = await start(env.client, tenant)
        res = await h.result()
    assert res.status == RunStatus.escalated
    assert "handoff" in res.summary


async def test_worker_restart_replays(env, tenant, acts) -> None:
    async with worker(env.client, acts, sticky=False):
        h, _rid = await start(env.client, tenant)
        await wait_state(h, "waiting_approval")
    # worker is gone; the workflow is parked durably in Temporal
    async with worker(env.client, acts, sticky=False):
        await _approve(h)
        res = await h.result()
    assert res.status == RunStatus.completed


async def test_cancel_signal(env, tenant, acts) -> None:
    async with worker(env.client, acts):
        h, _rid = await start(env.client, tenant)
        await wait_state(h, "waiting_approval")
        await h.signal(OrynRunWorkflow.cancel)
        res = await h.result()
    assert res.status == RunStatus.cancelled
    async with owner_session() as s:
        assert (await s.execute(select(Approval.status))).scalar_one() == "cancelled"


async def test_unqualified_lead_gets_nurture_email(env, tenant, acts) -> None:
    from oryn.models import SbMessage
    from tests.orchestration.wf_helpers import LEAD

    async with worker(env.client, acts):
        h, _ = await start(env.client, tenant, GOLDEN, {**LEAD, "budget_usd": 500, "requested_discount_pct": None})
        res = await h.result()
    assert res.status == RunStatus.completed and res.outcomes == ["lead_nurtured"]
    async with owner_session() as s:
        assert (await s.execute(select(SbMessage.subject))).scalar_one().startswith("Thanks for reaching out")


_ = WorkflowFailureError


async def test_handoff_satisfies_the_next_step_for_that_role(env, tenant, acts) -> None:
    """Regression: the NL-built lead workflow has an explicit scheduler step *and* the sales agent
    hands off to the scheduler. The scheduler must run once — one booking, one outcome."""
    from oryn.builder.examples import EXAMPLES
    from oryn.builder.grammar import compile_offline
    from oryn.models import Outcome

    definition = compile_offline(EXAMPLES[0]).definition.model_dump(mode="json", by_alias=True)
    async with worker(env.client, acts):
        h, rid = await start(env.client, tenant, definition)
        await _approve(h)
        res = await h.result()
    assert res.status == RunStatus.completed and res.outcomes == ["meeting_booked"]
    async with owner_session() as s:
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(Outcome))).scalar_one() == 1
        decisions = (
            (await s.execute(select(Span.name).where(Span.run_id == rid, Span.kind == SpanKind.decision)))
            .scalars()
            .all()
        )
    assert any("already handled" in d for d in decisions)


async def test_decision_arriving_before_the_workflow_sees_the_approval_is_kept(isolated_temporal_env, tenant, acts):
    """Review finding I1: a decision that lands between request_approval committing and the workflow
    processing its result was discarded, so the run escalated and auto-rejected."""
    from dataclasses import dataclass

    from temporalio import activity as act

    from oryn.orchestration.models import RequestApprovalInput

    env = isolated_temporal_env

    @dataclass
    class FastDecider(OrynActivities):
        @act.defn(name="request_approval")
        async def request_approval(self, inp: RequestApprovalInput):
            aid = await OrynActivities.request_approval(self, inp)
            handle = env.client.get_workflow_handle(act.info().workflow_id)
            await handle.signal(OrynRunWorkflow.decide_approval, ApprovalDecisionSignal(approval_id=aid, approved=True))
            return aid

    fast = FastDecider(acts.llm, acts.memory, acts.bus, acts.registry, acts.settings)
    async with worker(env.client, fast):
        h, rid = await start(env.client, tenant)
        res = await h.result()
    assert res.status == RunStatus.completed
    async with owner_session() as s:
        assert (await s.execute(select(SbDeal.discount_pct))).scalar_one() == 15
        escalations = (
            (await s.execute(select(Span.name).where(Span.run_id == rid, Span.name.like("%escalated%"))))
            .scalars()
            .all()
        )
    assert escalations == []


async def test_parallel_branches_can_each_wait_for_approval(env, tenant, acts) -> None:
    """Review finding I2: parallel branches shared one pending-approval slot, so one branch's
    approval overwrote the other's and its decision was ignored."""
    import asyncio

    from oryn.models import Approval

    definition = {
        "name": "two sales passes",
        "trigger": {"event": "lead.created"},
        "steps": [
            {
                "id": "both",
                "type": "parallel",
                "branches": [
                    {"id": "a", "type": "agent", "role": "sales", "goal": "Qualify"},
                    {"id": "b", "type": "agent", "role": "sales", "goal": "Qualify again"},
                ],
            }
        ],
    }
    async with worker(env.client, acts):
        h, _ = await start(env.client, tenant, definition)
        for _ in range(100):
            async with owner_session() as s:
                pending = (await s.execute(select(Approval.id).where(Approval.status == "pending"))).scalars().all()
            if len(pending) == 2:
                break
            await asyncio.sleep(0.1)
        assert len(pending) == 2
        for aid in pending:
            await h.signal(OrynRunWorkflow.decide_approval, ApprovalDecisionSignal(approval_id=aid, approved=True))
        res = await h.result()
    assert res.status == RunStatus.completed
    async with owner_session() as s:
        assert sorted((await s.execute(select(SbDeal.discount_pct))).scalars().all()) == [15, 15]
