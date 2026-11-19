from sqlalchemy import select

from oryn.agents.runner import MAX_AGENT_ITERATIONS, ActionOutcome, AgentStepInput, run_agent
from oryn.core.db import owner_session
from oryn.llm.types import LLMResult, ToolCall, Usage
from oryn.models import Agent, AgentRole, Memory, MemoryScope, SbDeal
from oryn.policies.approval import WorkflowPolicies
from tests.agents.conftest import LEAD, make_deps
from tests.fakes import FakeSpanSink


def _inp(t, run_id, role=AgentRole.sales, **kw) -> AgentStepInput:
    return AgentStepInput(
        tenant_id=t.id,
        run_id=run_id,
        step_key=kw.pop("step_key", "qualify"),
        agent_role=role,
        goal="Qualify the lead and propose a quote",
        blackboard={},
        trigger=LEAD,
        subject_keys=[(MemoryScope.contact, "contact:dana@example.com")],
        policies=WorkflowPolicies(),
        **kw,
    )


async def _run(session_for, t, inp, **deps_kw):
    cm, s, cs = await session_for(t.id)
    try:
        return await run_agent(inp, make_deps(s, cs, **deps_kw))
    finally:
        await cm.__aexit__(None, None, None)


async def test_sales_step_returns_pending_discount_approval(world, session_for) -> None:
    t, run_id = world
    out = await _run(session_for, t, _inp(t, run_id))
    assert out.status == "pending_action"
    assert out.pending_action.tool == "crm.apply_discount"
    assert "discount 15% exceeds 10% policy" in out.pending_action.requirement.reasons
    assert out.pending_action.idempotency_key.startswith(f"{run_id}:qualify:")
    assert [a.tool for a in out.executed_actions] == ["crm.upsert_contact", "crm.create_deal"]
    async with owner_session() as s:
        assert (await s.execute(select(SbDeal))).scalar_one().discount_pct == 0


async def test_resume_after_approval_hands_off(world, session_for) -> None:
    t, run_id = world
    first = await _run(session_for, t, _inp(t, run_id))
    p = first.pending_action
    resumed = await _run(
        session_for,
        t,
        _inp(
            t,
            run_id,
            resume_with=ActionOutcome(
                approved=True, result={"deal": {"discount_pct": "15"}}, tool_call_id=p.tool_call_id
            ),
        ),
    )
    assert resumed.status == "handoff"
    assert resumed.handoff.role == AgentRole.scheduler
    # each step output carries only its own blackboard updates; the workflow merges them
    assert first.blackboard_updates["qualified"] is True
    assert resumed.blackboard_updates["deal_amount_usd"] == 8200
    async with owner_session() as s:
        mem = (await s.execute(select(Memory))).scalars().all()
    assert len(mem) == 1 and "heat pump" in mem[0].content


async def test_resume_after_rejection_continues_without_discount(world, session_for) -> None:
    t, run_id = world
    first = await _run(session_for, t, _inp(t, run_id))
    resumed = await _run(
        session_for,
        t,
        _inp(
            t,
            run_id,
            resume_with=ActionOutcome(
                approved=False, comment="too generous", tool_call_id=first.pending_action.tool_call_id
            ),
        ),
    )
    assert resumed.status == "handoff"
    async with owner_session() as s:
        assert (await s.execute(select(SbDeal))).scalar_one().discount_pct == 0


class LoopingLLM:
    async def complete(self, **kw) -> LLMResult:
        n = len(kw["messages"])
        return LLMResult(
            text="",
            tool_calls=[ToolCall(id=f"c{n}", name="crm.find_contact", arguments={"email": "x@y.z"})],
            usage=Usage(input_tokens=10, output_tokens=5),
            model="m",
            simulated=True,
            stop_reason="tool_use",
        )


async def test_iteration_cap_escalates(world, session_for) -> None:
    t, run_id = world
    out = await _run(session_for, t, _inp(t, run_id), llm=LoopingLLM())
    assert out.status == "escalated"
    assert out.iterations == MAX_AGENT_ITERATIONS


async def test_budget_cap_escalates(world, session_for) -> None:
    t, run_id = world
    async with owner_session() as s:
        a = (await s.execute(select(Agent).where(Agent.role == AgentRole.sales))).scalar_one()
        a.max_tokens_per_run = 50
    out = await _run(session_for, t, _inp(t, run_id))
    assert out.status == "escalated" and "budget" in out.summary


async def test_spans_recorded(world, session_for) -> None:
    t, run_id = world
    sink = FakeSpanSink()
    await _run(session_for, t, _inp(t, run_id), sink=sink)
    kinds = sink.kinds()
    assert kinds.count("agent") == 1 and "llm_call" in kinds and "tool_call" in kinds
    assert not any(s["open"] for s in sink.spans.values())


async def test_scheduler_finishes_with_outcome(world, session_for) -> None:
    t, run_id = world
    bb = {"contact_email": "dana@example.com", "contact_name": "Dana Reyes", "deal_amount_usd": 8200}
    inp = _inp(t, run_id, role=AgentRole.scheduler, step_key="book")
    inp.blackboard = bb
    out = await _run(session_for, t, inp)
    assert out.status == "finished" and out.outcome == "meeting_booked" and out.outcome_value_usd == 8200
    assert [a.tool for a in out.executed_actions] == ["calendar.book", "messaging.send_email"]


async def test_missing_agent_fails_cleanly(world, session_for) -> None:
    t, run_id = world
    out = await _run(session_for, t, _inp(t, run_id, role=AgentRole.reporting))
    assert out.status == "failed" and "no enabled reporting agent" in out.summary


async def test_agent_heartbeats_every_iteration(world, session_for) -> None:
    """Review finding I5: one heartbeat per step let multi-call steps outlive the heartbeat timeout."""
    t, run_id = world
    beats: list[int] = []
    cm, s, cs = await session_for(t.id)
    try:
        deps = make_deps(s, cs)
        deps.heartbeat = lambda: beats.append(1)
        out = await run_agent(_inp(t, run_id), deps)
    finally:
        await cm.__aexit__(None, None, None)
    assert len(beats) >= out.iterations >= 3
