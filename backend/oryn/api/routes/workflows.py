import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from oryn.api.deps import TenantContext, require_role
from oryn.builder.drafts import draft_workflow
from oryn.builder.examples import EXAMPLES
from oryn.builder.grammar import DraftResult
from oryn.core.audit import record_audit
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Run, Workflow, WorkflowVersion
from oryn.workflows.dsl import WorkflowDefinition, validate_definition

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class DraftIn(BaseModel):
    text: str


class DefinitionIn(BaseModel):
    definition: dict[str, Any]
    source_text: str | None = None


class EnabledIn(BaseModel):
    enabled: bool


class WorkflowOut(BaseModel):
    id: uuid.UUID
    name: str
    trigger_event: str
    enabled: bool
    current_version: int | None
    runs_total: int = 0
    updated_at: datetime


class VersionOut(BaseModel):
    id: uuid.UUID
    version: int
    created_at: datetime
    source_text: str | None


class WorkflowDetail(WorkflowOut):
    definition: dict[str, Any] | None
    source_text: str | None
    versions: list[VersionOut]


def _validated(body: DefinitionIn) -> WorkflowDefinition:
    try:
        d = WorkflowDefinition.model_validate(body.definition)
    except ValidationError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"errors": [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]},
        ) from e
    if errors := validate_definition(d):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": errors})
    return d


async def _detail(s, wid: uuid.UUID) -> WorkflowDetail:
    wf = await s.get(Workflow, wid)
    if wf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow not found")
    await s.refresh(wf)  # pick up server-side updated_at after a write
    versions = (
        (
            await s.execute(
                select(WorkflowVersion)
                .where(WorkflowVersion.workflow_id == wid)
                .order_by(WorkflowVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    current = next((v for v in versions if v.id == wf.current_version_id), None)
    runs = (await s.execute(select(func.count()).select_from(Run).where(Run.workflow_id == wid))).scalar_one()
    return WorkflowDetail(
        id=wf.id,
        name=wf.name,
        trigger_event=wf.trigger_event,
        enabled=wf.enabled,
        current_version=current.version if current else None,
        runs_total=runs,
        updated_at=wf.updated_at,
        definition=current.definition if current else None,
        source_text=current.source_text if current else None,
        versions=[
            VersionOut(id=v.id, version=v.version, created_at=v.created_at, source_text=v.source_text) for v in versions
        ],
    )


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[WorkflowOut]:
    async with tenant_session(ctx.tenant_id) as s:
        runs = dict((await s.execute(select(Run.workflow_id, func.count()).group_by(Run.workflow_id))).all())
        rows = await s.execute(
            select(Workflow, WorkflowVersion.version)
            .outerjoin(WorkflowVersion, WorkflowVersion.id == Workflow.current_version_id)
            .order_by(Workflow.name)
        )
        return [
            WorkflowOut(
                id=w.id,
                name=w.name,
                trigger_event=w.trigger_event,
                enabled=w.enabled,
                current_version=v,
                runs_total=runs.get(w.id, 0),
                updated_at=w.updated_at,
            )
            for w, v in rows
        ]


@router.get("/examples", response_model=list[str])
async def examples(ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[str]:
    return EXAMPLES


@router.post("/draft", response_model=DraftResult)
async def draft(body: DraftIn, ctx: TenantContext = Depends(require_role(Role.admin))) -> DraftResult:
    return await draft_workflow(body.text)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(workflow_id: uuid.UUID, ctx: TenantContext = Depends(require_role(Role.viewer))):
    async with tenant_session(ctx.tenant_id) as s:
        return await _detail(s, workflow_id)


@router.post("", response_model=WorkflowDetail, status_code=201)
async def create_workflow(body: DefinitionIn, ctx: TenantContext = Depends(require_role(Role.admin))):
    d = _validated(body)
    async with tenant_session(ctx.tenant_id) as s:
        wf = Workflow(tenant_id=ctx.tenant_id, name=d.name, trigger_event=d.trigger.event, enabled=True)
        s.add(wf)
        await s.flush()
        v = WorkflowVersion(
            tenant_id=ctx.tenant_id,
            workflow_id=wf.id,
            version=1,
            definition=d.model_dump(mode="json", by_alias=True),
            source_text=body.source_text,
            created_by=ctx.user_id,
        )
        s.add(v)
        await s.flush()
        wf.current_version_id = v.id
        await record_audit(s, ctx, "workflow.created", "workflow", wf.id, after={"name": d.name})
        await s.flush()
        return await _detail(s, wf.id)


@router.post("/{workflow_id}/versions", response_model=WorkflowDetail, status_code=201)
async def new_version(
    workflow_id: uuid.UUID, body: DefinitionIn, ctx: TenantContext = Depends(require_role(Role.admin))
):
    d = _validated(body)
    async with tenant_session(ctx.tenant_id) as s:
        wf = await s.get(Workflow, workflow_id)
        if wf is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow not found")
        latest = (
            await s.execute(select(func.max(WorkflowVersion.version)).where(WorkflowVersion.workflow_id == workflow_id))
        ).scalar_one() or 0
        v = WorkflowVersion(
            tenant_id=ctx.tenant_id,
            workflow_id=wf.id,
            version=latest + 1,
            definition=d.model_dump(mode="json", by_alias=True),
            source_text=body.source_text,
            created_by=ctx.user_id,
        )
        s.add(v)
        await s.flush()
        wf.current_version_id, wf.name, wf.trigger_event = v.id, d.name, d.trigger.event
        await record_audit(s, ctx, "workflow.versioned", "workflow", wf.id, after={"version": v.version})
        await s.flush()
        return await _detail(s, wf.id)


@router.patch("/{workflow_id}", response_model=WorkflowDetail)
async def set_enabled(workflow_id: uuid.UUID, body: EnabledIn, ctx: TenantContext = Depends(require_role(Role.admin))):
    async with tenant_session(ctx.tenant_id) as s:
        wf = await s.get(Workflow, workflow_id)
        if wf is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow not found")
        before = wf.enabled
        wf.enabled = body.enabled
        await record_audit(
            s, ctx, "workflow.toggled", "workflow", wf.id, {"enabled": before}, {"enabled": body.enabled}
        )
        await s.flush()
        return await _detail(s, wf.id)
