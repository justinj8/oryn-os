from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from oryn.agents.state import ExecutedAction
from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import Approval, Outcome, OutcomeType, Run, RunStatus, SbCalendarEvent, SbMessage, Span, SpanKind
from oryn.orchestration.models import (
    CompensateInput,
    ExecuteActionInput,
    FinalizeInput,
    NotifyInput,
    OutcomeInput,
    RequestApprovalInput,
)
from oryn.workflows.dsl import NotifyStep

ENV = ActivityEnvironment()
SLOT = {"starts_at": "2026-11-17T15:00:00Z", "ends_at": "2026-11-17T15:30:00Z", "title": "Consult"}


def _exec(t, rid, tool="calendar.book", args=SLOT, key="k1") -> ExecuteActionInput:
    return ExecuteActionInput(tenant_id=t.id, run_id=rid, agent_id=None, tool=tool, args=args, idempotency_key=key)


async def test_execute_action_idempotent_across_retries(acts, tenant, run_row) -> None:
    r1 = await ENV.run(acts.execute_action, _exec(tenant, run_row))
    r2 = await ENV.run(acts.execute_action, _exec(tenant, run_row))
    assert r1["id"] == r2["id"]
    async with owner_session() as s:
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1


async def test_execute_action_non_retryable_maps_to_application_error(acts, tenant, run_row, invoice) -> None:
    with pytest.raises(ApplicationError) as ei:
        await ENV.run(
            acts.execute_action,
            _exec(tenant, run_row, "billing.issue_refund", {"invoice_id": str(invoice), "amount_usd": 900}),
        )
    assert ei.value.non_retryable is True


async def test_execute_action_bad_args_non_retryable(acts, tenant, run_row) -> None:
    with pytest.raises(ApplicationError) as ei:
        await ENV.run(acts.execute_action, _exec(tenant, run_row, "calendar.book", {"title": "x"}))
    assert ei.value.non_retryable is True


async def test_request_approval_idempotent(acts, tenant, run_row) -> None:
    inp = RequestApprovalInput(
        tenant_id=tenant.id,
        run_id=run_row,
        step_id="qualify",
        tool="crm.apply_discount",
        args={"discount_pct": 15},
        idempotency_key="k-approve",
        description="Discount 15%",
        reasons=["discount 15% exceeds 10% policy"],
        min_role=Role.operator,
        expires_in_s=3600,
    )
    a1 = await ENV.run(acts.request_approval, inp)
    a2 = await ENV.run(acts.request_approval, inp)
    assert a1 == a2
    async with owner_session() as s:
        rows = (await s.execute(select(Approval))).scalars().all()
        spans = (await s.execute(select(Span.kind))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "pending" and rows[0].min_role == Role.operator
    assert SpanKind.approval in spans


async def test_finalize_run_sums_costs(acts, tenant, run_row) -> None:
    async with owner_session() as s:
        for c in ("0.01", "0.02", "0.005"):
            s.add(
                Span(
                    tenant_id=tenant.id,
                    run_id=run_row,
                    kind=SpanKind.llm_call,
                    name="m",
                    status="ok",
                    input_tokens=10,
                    output_tokens=5,
                    cost_usd=Decimal(c),
                    simulated=True,
                    started_at=datetime.now(UTC),
                )
            )
    await ENV.run(
        acts.finalize_run,
        FinalizeInput(
            tenant_id=tenant.id,
            run_id=run_row,
            status=RunStatus.completed,
            summary="ok",
            blackboard={"qualified": True},
        ),
    )
    async with owner_session() as s:
        run = await s.get(Run, run_row)
    assert run.total_cost_usd == Decimal("0.035") and run.total_input_tokens == 30
    assert run.status == RunStatus.completed and run.ended_at is not None and run.simulated_cost is True
    assert run.blackboard == {"qualified": True}


async def test_send_notification_renders_template(acts, tenant, run_row) -> None:
    step = NotifyStep(id="n", channel="email", template="nurture")
    await ENV.run(
        acts.send_notification,
        NotifyInput(
            tenant_id=tenant.id,
            run_id=run_row,
            step=step,
            trigger={"name": "Dana Reyes", "email": "dana@example.com"},
            blackboard={},
        ),
    )
    async with owner_session() as s:
        msg = (await s.execute(select(SbMessage))).scalar_one()
    assert msg.to_addr == "dana@example.com" and "Dana" in msg.body


async def test_record_outcome_uses_minutes_saved(acts, tenant, run_row) -> None:
    await ENV.run(
        acts.record_outcome,
        OutcomeInput(tenant_id=tenant.id, run_id=run_row, type=OutcomeType.meeting_booked, value_usd=8200),
    )
    async with owner_session() as s:
        o = (await s.execute(select(Outcome))).scalar_one()
    assert o.value_usd == Decimal(8200) and o.minutes_saved == 20


async def test_compensate_cancels_bookings(acts, tenant, run_row) -> None:
    booked = await ENV.run(acts.execute_action, _exec(tenant, run_row))
    await ENV.run(
        acts.compensate,
        CompensateInput(
            tenant_id=tenant.id,
            run_id=run_row,
            actions=[ExecutedAction(tool="calendar.book", idempotency_key="k1", result=booked)],
        ),
    )
    async with owner_session() as s:
        assert (await s.execute(select(SbCalendarEvent.status))).scalar_one() == "cancelled"


def test_every_activity_is_registered(acts) -> None:
    import inspect

    defined = {
        name
        for name, fn in inspect.getmembers(type(acts), inspect.isfunction)
        if hasattr(fn, "__temporal_activity_definition")
    }
    assert defined and {f.__name__ for f in acts.all()} == defined


async def test_retry_closes_spans_left_open_by_a_crashed_attempt(acts, tenant, run_row) -> None:
    """A worker crash leaves the attempt's spans 'running'. The next attempt marks them interrupted."""
    import dataclasses

    from oryn.agents.state import AgentStepInput
    from oryn.models import AgentRole

    async with owner_session() as s:
        agent_span = Span(
            tenant_id=tenant.id,
            run_id=run_row,
            kind=SpanKind.agent,
            name="Scheduler · book",
            status="running",
            attempt=1,
            started_at=datetime.now(UTC),
        )
        s.add(agent_span)
        await s.flush()
        s.add(
            Span(
                tenant_id=tenant.id,
                run_id=run_row,
                parent_span_id=agent_span.id,
                kind=SpanKind.tool_call,
                name="calendar.book",
                status="running",
                attempt=1,
                started_at=datetime.now(UTC),
            )
        )
        s.add(
            Span(
                tenant_id=tenant.id,
                run_id=run_row,
                kind=SpanKind.agent,
                name="Sales · other-step",
                status="running",
                attempt=1,
                started_at=datetime.now(UTC),
            )
        )
    env = ActivityEnvironment()
    env.info = dataclasses.replace(env.info, attempt=2)
    await env.run(
        acts.run_agent_step,
        AgentStepInput(
            tenant_id=tenant.id, run_id=run_row, step_key="book", agent_role=AgentRole.scheduler, goal="Book a consult"
        ),
    )
    async with owner_session() as s:
        rows = {(sp.name, sp.attempt): sp.status for sp in (await s.execute(select(Span))).scalars()}
    assert rows[("Scheduler · book", 1)] == "interrupted"
    assert rows[("calendar.book", 1)] == "interrupted"
    assert rows[("Sales · other-step", 1)] == "running"  # another step's spans are left alone


async def test_update_approval_status_returns_final_status(acts, tenant, run_row) -> None:
    from oryn.models import ApprovalStatus
    from oryn.orchestration.models import UpdateApprovalInput

    inp = RequestApprovalInput(
        tenant_id=tenant.id,
        run_id=run_row,
        step_id="s",
        tool=None,
        idempotency_key="k-final",
        description="Gate",
        min_role=Role.operator,
        expires_in_s=60,
    )
    aid = await ENV.run(acts.request_approval, inp)
    upd = UpdateApprovalInput(
        tenant_id=tenant.id, run_id=run_row, approval_id=aid, status=ApprovalStatus.rejected, comment="timed out"
    )
    assert await ENV.run(acts.update_approval_status, upd) == "rejected"
    # Already decided: the earlier decision is reported and nothing changes.
    upd2 = upd.model_copy(update={"status": ApprovalStatus.approved})
    assert await ENV.run(acts.update_approval_status, upd2) == "rejected"


async def test_record_outcome_is_idempotent(acts, tenant, run_row) -> None:
    """Review finding I4: a retry after the commit inserted a second outcome and inflated pipeline $."""
    inp = OutcomeInput(
        tenant_id=tenant.id,
        run_id=run_row,
        type=OutcomeType.meeting_booked,
        value_usd=8200,
        key=f"{run_row}:book:meeting_booked",
    )
    await ENV.run(acts.record_outcome, inp)
    await ENV.run(acts.record_outcome, inp)
    async with owner_session() as s:
        assert (await s.execute(select(func.count()).select_from(Outcome))).scalar_one() == 1
