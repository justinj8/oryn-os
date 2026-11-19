"""Event ingest: the front door for everything that starts work.

Webhooks, simulators, the traffic generator and the seed script all call ``ingest_event``.
It is idempotent twice over: the event row is unique per (tenant, idempotency key), and the
Temporal workflow id is derived from the event id, so even a race between two deliveries
can only ever start one run per workflow.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from oryn.core.db import tenant_session
from oryn.core.logging import log
from oryn.models import Event, Run, RunStatus, Workflow, WorkflowVersion
from oryn.observability.bus import LiveEvent, get_event_bus
from oryn.orchestration.client import get_task_queue
from oryn.orchestration.models import RunInput
from oryn.workflows.dsl import WorkflowDefinition


@dataclass
class IngestResult:
    event_id: uuid.UUID
    created: bool
    run_ids: list[uuid.UUID]


def _matches(filter_: dict[str, Any], payload: dict[str, Any]) -> bool:
    return all(str(payload.get(k)) == str(v) for k, v in filter_.items())


def _title(name: str, payload: dict[str, Any]) -> str:
    who = payload.get("name") or payload.get("company") or payload.get("email") or payload.get("subject")
    return f"{name} for {who}" if who else name


async def ingest_event(
    client: Client,
    tenant_id: uuid.UUID,
    type_: str,
    source: str,
    payload: dict[str, Any],
    idempotency_key: str,
    *,
    started_by_user_id: uuid.UUID | None = None,
    time_offset_seconds: float = 0,
    time_scale: float = 1.0,
    task_queue: str | None = None,
) -> IngestResult:
    now = datetime.now(UTC) + timedelta(seconds=time_offset_seconds)
    to_start: list[tuple[Run, RunInput]] = []
    async with tenant_session(tenant_id) as s:
        event_id = (
            await s.execute(
                insert(Event)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    type=type_,
                    source=source,
                    idempotency_key=idempotency_key,
                    payload=payload,
                    received_at=now,
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "idempotency_key"])
                .returning(Event.id)
            )
        ).scalar_one_or_none()
        if event_id is None:  # duplicate delivery: report what the first one started
            existing = (await s.execute(select(Event).where(Event.idempotency_key == idempotency_key))).scalar_one()
            runs = (await s.execute(select(Run).where(Run.trigger_event_id == existing.id))).scalars().all()
            # A provider retry is also our chance to recover runs whose workflow never started.
            # REJECT_DUPLICATE on the deterministic workflow id keeps this safe to repeat.
            for run in runs:
                if run.status == RunStatus.failed and (run.error or "").startswith("could not start"):
                    version = await s.get(WorkflowVersion, run.workflow_version_id) if run.workflow_version_id else None
                    if version is None:
                        continue
                    run.status, run.error, run.ended_at = RunStatus.running, None, None
                    to_start.append(
                        (
                            run,
                            RunInput(
                                tenant_id=tenant_id,
                                run_id=run.id,
                                workflow_version_id=version.id,
                                definition=WorkflowDefinition.model_validate(version.definition),
                                trigger=existing.payload,
                                trigger_event_id=existing.id,
                                started_by_user_id=run.started_by_user_id,
                                time_offset_seconds=time_offset_seconds,
                                time_scale=time_scale,
                            ),
                        )
                    )
            if not to_start:
                return IngestResult(existing.id, False, [r.id for r in runs])
            event_id, created, all_run_ids = existing.id, False, [r.id for r in runs]
        else:
            created, all_run_ids = True, []

        if created:
            rows = await s.execute(
                select(Workflow, WorkflowVersion)
                .join(WorkflowVersion, WorkflowVersion.id == Workflow.current_version_id)
                .where(Workflow.trigger_event == type_, Workflow.enabled.is_(True))
            )
            for wf, ver in rows:
                definition = WorkflowDefinition.model_validate(ver.definition)
                if not _matches(definition.trigger.filter, payload):
                    continue
                run = Run(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    workflow_id=wf.id,
                    workflow_version_id=ver.id,
                    kind="workflow",
                    title=_title(wf.name, payload)[:300],
                    temporal_workflow_id=f"{tenant_id}:{wf.id}:{event_id}",
                    status=RunStatus.running,
                    trigger_event_id=event_id,
                    started_by_user_id=started_by_user_id,
                    started_at=now,
                )
                s.add(run)
                to_start.append(
                    (
                        run,
                        RunInput(
                            tenant_id=tenant_id,
                            run_id=run.id,
                            workflow_version_id=ver.id,
                            definition=definition,
                            trigger=payload,
                            trigger_event_id=event_id,
                            started_by_user_id=started_by_user_id,
                            time_offset_seconds=time_offset_seconds,
                            time_scale=time_scale,
                        ),
                    )
                )

    # Start workflows only after the rows are committed, so activities can see them.
    from oryn.orchestration.run_workflow import OrynRunWorkflow

    bus = get_event_bus()
    await bus.publish(LiveEvent(type="event.received", tenant_id=tenant_id, data={"type": type_, "source": source}))
    for run, inp in to_start:
        try:
            await client.start_workflow(
                OrynRunWorkflow.run,
                inp,
                id=run.temporal_workflow_id,
                task_queue=task_queue or get_task_queue(),
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowAlreadyStartedError:
            pass
        except Exception as e:
            log.error("ingest.start_failed", run_id=str(run.id), error=str(e))
            async with tenant_session(tenant_id) as s:
                r = await s.get(Run, run.id)
                if r:
                    r.status, r.error, r.ended_at = RunStatus.failed, f"could not start: {e}", datetime.now(UTC)
            continue
        await bus.publish(LiveEvent(type="run.started", tenant_id=tenant_id, run_id=run.id, data={"title": run.title}))
    return IngestResult(event_id, created, all_run_ids or [r.id for r, _ in to_start])
