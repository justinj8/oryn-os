"""Temporal activities. Every side effect in Oryn OS happens here, and every one is idempotent.

Activities are methods on ``OrynActivities`` so tests and the worker can inject dependencies
(LLM provider, memory store, event bus). Each opens its own tenant-scoped transaction.
"""

import inspect
import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from oryn.agents.runner import AgentDeps, run_agent
from oryn.agents.state import AgentStepInput, AgentStepOutput
from oryn.connectors.errors import ErrorClass, classify_error
from oryn.connectors.registry import build_connector_set
from oryn.core.config import Settings, get_settings
from oryn.core.db import tenant_session
from oryn.core.logging import log
from oryn.llm.factory import get_llm_provider
from oryn.llm.types import LLMProvider
from oryn.memory.embeddings import HashingEmbedder
from oryn.memory.store import MemoryStore
from oryn.models import (
    Approval,
    ApprovalStatus,
    Conversation,
    Outcome,
    Run,
    RunStatus,
    SbActionLog,
    SbMessage,
    Span,
    SpanKind,
    Tenant,
)
from oryn.observability.bus import EventBus, LiveEvent, get_event_bus
from oryn.observability.clock import OffsetClock
from oryn.observability.spans import DbSpanSink
from oryn.orchestration.models import (
    ChannelMessageInput,
    CompensateInput,
    ExecuteActionInput,
    FinalizeInput,
    MarkRunInput,
    NotifyInput,
    OutcomeInput,
    RequestApprovalInput,
    SpanEventInput,
    UpdateApprovalInput,
)
from oryn.orchestration.templates import notification_scope, render
from oryn.tools.registry import ToolArgsError, ToolContext, ToolRegistry, default_registry

DEFAULT_MINUTES_SAVED = {
    "meeting_booked": 20,
    "deal_created": 15,
    "ticket_resolved": 12,
    "invoice_collected": 10,
    "report_delivered": 45,
    "lead_nurtured": 8,
}


def _to_application_error(e: BaseException) -> ApplicationError:
    cls = classify_error(e)
    if cls is ErrorClass.non_retryable:
        return ApplicationError(str(e), type="NonRetryable", non_retryable=True)
    if cls is ErrorClass.rate_limited:
        return ApplicationError(str(e), type="RateLimited", next_retry_delay=timedelta(seconds=10))
    return ApplicationError(str(e), type="Retryable")


@dataclass
class OrynActivities:
    llm: LLMProvider
    memory: MemoryStore
    bus: EventBus
    registry: ToolRegistry
    settings: Settings

    @classmethod
    def default(cls, settings: Settings | None = None) -> "OrynActivities":
        settings = settings or get_settings()
        return cls(
            get_llm_provider(settings), MemoryStore(HashingEmbedder()), get_event_bus(), default_registry(), settings
        )

    def all(self) -> list:
        """Every ``@activity.defn`` method, bound to this instance (registration can't drift)."""
        return [
            getattr(self, name)
            for name, fn in inspect.getmembers(type(self), inspect.isfunction)
            if hasattr(fn, "__temporal_activity_definition")
        ]

    def _sink(self, tenant_id: uuid.UUID, run_id: uuid.UUID, offset: float) -> DbSpanSink:
        attempt = activity.info().attempt if activity.in_activity() else 1
        return DbSpanSink(tenant_id, run_id, self.bus, OffsetClock(offset), attempt=attempt)

    async def _publish(self, type_: str, tenant_id: uuid.UUID, run_id: uuid.UUID | None, data: dict) -> None:
        await self.bus.publish(LiveEvent(type=type_, tenant_id=tenant_id, run_id=run_id, data=data))  # type: ignore[arg-type]

    # ------------------------------------------------------------------ run bookkeeping
    @activity.defn(name="mark_run")
    async def mark_run(self, inp: MarkRunInput) -> None:
        async with tenant_session(inp.tenant_id) as s:
            run = await s.get(Run, inp.run_id)
            terminal = (RunStatus.completed, RunStatus.failed, RunStatus.cancelled, RunStatus.escalated)
            if run and (inp.reopen or run.status not in terminal):
                run.status = inp.status
                if inp.reopen:
                    run.ended_at = None
        await self._publish(
            "run.updated", inp.tenant_id, inp.run_id, {"status": inp.status.value, "current_step": inp.current_step}
        )

    @activity.defn(name="record_span_event")
    async def record_span_event(self, inp: SpanEventInput) -> None:
        await self._sink(inp.tenant_id, inp.run_id, inp.time_offset_seconds).event(
            SpanKind(inp.kind), inp.name, inp.data, status=inp.status
        )

    # ------------------------------------------------------------------ agents
    @activity.defn(name="run_agent_step")
    async def run_agent_step(self, inp: AgentStepInput) -> AgentStepOutput:
        if activity.in_activity():
            activity.heartbeat()
        sink = self._sink(inp.tenant_id, inp.run_id, inp.time_offset_seconds)
        if sink.attempt > 1:
            await sink.event(
                SpanKind.retry,
                f"retry {inp.step_key} (attempt {sink.attempt})",
                {"attempt": sink.attempt},
                status="error",
            )
        clock = OffsetClock(inp.time_offset_seconds)
        # Fault injection is seeded per (run, step, attempt): demos and tests replay identically.
        rng = random.Random(f"{inp.run_id}:{inp.step_key}:{sink.attempt}")
        try:
            async with tenant_session(inp.tenant_id) as s:
                connectors = await build_connector_set(
                    s, inp.tenant_id, self.settings, now=clock.now, rng=rng, attempt=sink.attempt
                )
                deps = AgentDeps(
                    llm=self.llm,
                    registry=self.registry,
                    memory=self.memory,
                    spans=sink,
                    session=s,
                    connectors=connectors,
                    settings=self.settings,
                )
                return await run_agent(inp, deps)
        except ApplicationError:
            raise
        except Exception as e:
            log.warning("activity.run_agent_step.failed", error=str(e), step=inp.step_key)
            raise _to_application_error(e) from e

    # ------------------------------------------------------------------ approvals
    @activity.defn(name="request_approval")
    async def request_approval(self, inp: RequestApprovalInput) -> uuid.UUID:
        clock = OffsetClock(inp.time_offset_seconds)
        async with tenant_session(inp.tenant_id) as s:
            existing = (
                await s.execute(select(Approval).where(Approval.idempotency_key == inp.idempotency_key))
            ).scalar_one_or_none()
            if existing:
                return existing.id
            now = clock.now()
            a = Approval(
                tenant_id=inp.tenant_id,
                run_id=inp.run_id,
                step_id=inp.step_id,
                action_tool=inp.tool,
                action_args=inp.args,
                description=inp.description,
                idempotency_key=inp.idempotency_key,
                risk_reasons=inp.reasons,
                min_role=inp.min_role,
                status=ApprovalStatus.pending,
                requested_by_agent_id=inp.agent_id,
                requested_at=now,
                expires_at=now + timedelta(seconds=inp.expires_in_s),
                escalation_level=0,
            )
            s.add(a)
            await s.flush()
            approval_id = a.id
        await self._sink(inp.tenant_id, inp.run_id, inp.time_offset_seconds).event(
            SpanKind.approval,
            f"approval requested: {inp.description}",
            {"approval_id": str(approval_id), "min_role": inp.min_role.value, "reasons": inp.reasons},
        )
        await self._publish(
            "approval.requested",
            inp.tenant_id,
            inp.run_id,
            {"approval_id": str(approval_id), "description": inp.description, "min_role": inp.min_role.value},
        )
        return approval_id

    @activity.defn(name="update_approval_status")
    async def update_approval_status(self, inp: UpdateApprovalInput) -> str:
        """Changes a *pending* approval and returns the status it ends up in. If a human already
        decided it, nothing changes and their decision is returned (decisions win races)."""
        clock = OffsetClock(inp.time_offset_seconds)
        async with tenant_session(inp.tenant_id) as s:
            a = await s.get(Approval, inp.approval_id)
            if a is None:
                return "missing"
            if a.status != ApprovalStatus.pending:
                return a.status.value
            a.status = inp.status
            if inp.min_role is not None:
                a.min_role = inp.min_role
            if inp.escalation_level is not None:
                a.escalation_level = inp.escalation_level
            if inp.expires_in_s is not None:
                a.expires_at = clock.now() + timedelta(seconds=inp.expires_in_s)
            if inp.status != ApprovalStatus.pending:
                a.decided_at, a.comment = clock.now(), inp.comment
        await self._publish(
            "approval.decided" if inp.status != ApprovalStatus.pending else "approval.requested",
            inp.tenant_id,
            inp.run_id,
            {"approval_id": str(inp.approval_id), "status": inp.status.value},
        )

    # ------------------------------------------------------------------ side effects
    @activity.defn(name="execute_action")
    async def execute_action(self, inp: ExecuteActionInput) -> dict:
        sink = self._sink(inp.tenant_id, inp.run_id, inp.time_offset_seconds)
        span = await sink.start(SpanKind.tool_call, f"{inp.tool} (approved)", inp.args, None, inp.agent_id)
        clock = OffsetClock(inp.time_offset_seconds)
        try:
            async with tenant_session(inp.tenant_id) as s:
                connectors = await build_connector_set(s, inp.tenant_id, self.settings, now=clock.now)
                ctx = ToolContext(
                    tenant_id=inp.tenant_id,
                    run_id=inp.run_id,
                    agent_id=inp.agent_id,
                    session=s,
                    connectors=connectors,
                    idempotency_key=inp.idempotency_key,
                )
                result = await self.registry.invoke(inp.tool, ctx, inp.args)
        except ToolArgsError as e:
            await sink.end(span, {"error": str(e)}, status="error")
            raise ApplicationError(str(e), type="NonRetryable", non_retryable=True) from e
        except Exception as e:
            await sink.end(span, {"error": str(e), "class": classify_error(e).value}, status="error")
            raise _to_application_error(e) from e
        await sink.end(span, result)
        return result

    @activity.defn(name="send_notification")
    async def send_notification(self, inp: NotifyInput) -> None:
        scope = notification_scope(inp.trigger, inp.blackboard)
        subject, body = render(inp.step.template, scope)
        if inp.step.channel == "email":
            to = (
                render(inp.step.to, scope)[1]
                if inp.step.to
                else (inp.trigger.get("email") or inp.blackboard.get("contact_email"))
            )
        else:
            to = (
                render(inp.step.to, scope)[1]
                if inp.step.to
                else (inp.trigger.get("phone") or inp.blackboard.get("contact_phone"))
            )
        sink = self._sink(inp.tenant_id, inp.run_id, inp.time_offset_seconds)
        if not to:
            await sink.event(SpanKind.notify, f"notify skipped: no {inp.step.channel} address", status="error")
            return
        key = f"{inp.run_id}:{inp.step.id}:notify"
        async with tenant_session(inp.tenant_id) as s:
            connectors = await build_connector_set(
                s, inp.tenant_id, self.settings, now=OffsetClock(inp.time_offset_seconds).now
            )
            if inp.step.channel == "email":
                await connectors.messaging.send_email(to, subject, body, key)
            else:
                await connectors.messaging.send_sms(to, body, key)
        await sink.event(
            SpanKind.notify, f"{inp.step.channel} → {to}", {"subject": subject, "template": inp.step.template}
        )

    @activity.defn(name="channel_message")
    async def channel_message(self, inp: ChannelMessageInput) -> None:
        """Logs a conversation turn to the transcript; with ``deliver`` it also sends it (follow-ups)."""
        key = f"conv:{inp.conversation_id}:{inp.direction}:{inp.message_id}"
        clock = OffsetClock(inp.time_offset_seconds)
        async with tenant_session(inp.tenant_id) as s:
            if (await s.execute(select(SbActionLog.id).where(SbActionLog.idempotency_key == key))).first():
                return
            if inp.deliver and inp.channel in ("sms", "email") and inp.address:
                connectors = await build_connector_set(s, inp.tenant_id, self.settings, now=clock.now)
                if inp.channel == "sms":
                    await connectors.messaging.send_sms(inp.address, inp.body, key, inp.conversation_id)
                else:
                    await connectors.messaging.send_email(
                        inp.address, "Following up", inp.body, key, inp.conversation_id
                    )
            else:
                s.add(
                    SbMessage(
                        tenant_id=inp.tenant_id,
                        channel=inp.channel,
                        direction=inp.direction,
                        to_addr=inp.address if inp.direction == "out" else None,
                        from_addr=inp.address if inp.direction == "in" else None,
                        body=inp.body,
                        conversation_id=inp.conversation_id,
                        sent_at=clock.now(),
                    )
                )
                s.add(SbActionLog(tenant_id=inp.tenant_id, tool="channel_message", idempotency_key=key, result={}))
            conv = await s.get(Conversation, inp.conversation_id)
            if conv:
                conv.last_message_at = clock.now()
        await self._publish(
            "message.sent",
            inp.tenant_id,
            inp.run_id,
            {"conversation_id": str(inp.conversation_id), "direction": inp.direction},
        )

    @activity.defn(name="record_outcome")
    async def record_outcome(self, inp: OutcomeInput) -> None:
        async with tenant_session(inp.tenant_id) as s:
            tenant = await s.get(Tenant, inp.tenant_id)
            minutes_map = {
                **DEFAULT_MINUTES_SAVED,
                **((tenant.settings or {}).get("minutes_saved_by_outcome", {}) if tenant else {}),
            }
            s.add(
                Outcome(
                    tenant_id=inp.tenant_id,
                    run_id=inp.run_id,
                    type=inp.type,
                    value_usd=Decimal(str(inp.value_usd or 0)),
                    minutes_saved=int(minutes_map.get(inp.type, 0)),
                    occurred_at=OffsetClock(inp.time_offset_seconds).now(),
                )
            )

    @activity.defn(name="compensate")
    async def compensate(self, inp: CompensateInput) -> None:
        sink = self._sink(inp.tenant_id, inp.run_id, inp.time_offset_seconds)
        async with tenant_session(inp.tenant_id) as s:
            connectors = await build_connector_set(s, inp.tenant_id, self.settings)
            for a in reversed(inp.actions):
                if a.tool == "calendar.book" and a.result.get("id"):
                    try:
                        async with s.begin_nested():
                            await connectors.calendar.cancel(
                                uuid.UUID(a.result["id"]), f"{a.idempotency_key}:compensate"
                            )
                        await sink.event(SpanKind.decision, f"compensated: cancelled booking {a.result['id']}")
                    except Exception as e:  # best effort: log and keep compensating the rest
                        await sink.event(
                            SpanKind.error, f"compensation failed for {a.tool}", {"error": str(e)}, status="error"
                        )

    @activity.defn(name="finalize_run")
    async def finalize_run(self, inp: FinalizeInput) -> None:
        async with tenant_session(inp.tenant_id) as s:
            run = await s.get(Run, inp.run_id)
            if run is None:
                return
            spans = (await s.execute(select(Span).where(Span.run_id == inp.run_id))).scalars().all()
            llm = [x for x in spans if x.kind == SpanKind.llm_call]
            run.total_input_tokens = sum(x.input_tokens for x in llm)
            run.total_output_tokens = sum(x.output_tokens for x in llm)
            run.total_cost_usd = sum((x.cost_usd for x in llm), Decimal(0))
            run.simulated_cost = all(x.simulated for x in llm) if llm else True
            run.status, run.outcome_summary, run.error = inp.status, inp.summary, inp.error
            run.blackboard = inp.blackboard
            run.ended_at = OffsetClock(inp.time_offset_seconds).now()
        await self._publish(
            "run.updated", inp.tenant_id, inp.run_id, {"status": inp.status.value, "summary": inp.summary}
        )
