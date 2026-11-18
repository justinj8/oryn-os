import fnmatch
import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select

from oryn.api.deps import TenantContext, require_role
from oryn.core.audit import record_audit
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Agent, AgentRole, Autonomy, Memory
from oryn.tools.registry import default_registry

router = APIRouter(prefix="/api", tags=["agents"])


def _check_tools(patterns: list[str]) -> list[str]:
    names = [s.name for s in default_registry().all_specs() if not s.is_control]
    bad = [p for p in patterns if not any(fnmatch.fnmatchcase(n, p) for n in names)]
    if bad:
        raise ValueError(f"unknown tools: {', '.join(bad)}")
    return patterns


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    role: AgentRole
    channels: list[str]
    model: str
    system_prompt: str
    allowed_tools: list[str]
    autonomy: Autonomy
    max_tokens_per_run: int
    max_cost_usd_per_run: Decimal
    enabled: bool
    updated_at: datetime

    @classmethod
    def of(cls, a: Agent) -> "AgentOut":
        return cls(
            id=a.id,
            name=a.name,
            role=a.role,
            channels=a.channels or [],
            model=a.model,
            system_prompt=a.system_prompt,
            allowed_tools=a.allowed_tools or [],
            autonomy=a.autonomy,
            max_tokens_per_run=a.max_tokens_per_run,
            max_cost_usd_per_run=a.max_cost_usd_per_run,
            enabled=a.enabled,
            updated_at=a.updated_at,
        )


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: AgentRole
    channels: list[str] = []
    model: str | None = None
    system_prompt: str = ""
    allowed_tools: list[str] = []
    autonomy: Autonomy = Autonomy.act_with_approval
    max_tokens_per_run: int = Field(20000, ge=500, le=1_000_000)
    max_cost_usd_per_run: Decimal = Field(Decimal("0.50"), ge=0, le=100)

    @field_validator("allowed_tools")
    @classmethod
    def _tools(cls, v: list[str]) -> list[str]:
        return _check_tools(v)


class AgentPatch(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    autonomy: Autonomy | None = None
    model: str | None = None
    max_tokens_per_run: int | None = Field(None, ge=500, le=1_000_000)
    max_cost_usd_per_run: Decimal | None = Field(None, ge=0, le=100)
    enabled: bool | None = None

    @field_validator("allowed_tools")
    @classmethod
    def _tools(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _check_tools(v)


class ToolOut(BaseModel):
    name: str
    description: str
    risk: str
    side_effect: bool
    connector: str | None


class MemoryOut(BaseModel):
    id: uuid.UUID
    scope: str
    subject_key: str
    content: str
    source_run_id: uuid.UUID | None
    created_at: datetime


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[AgentOut]:
    async with tenant_session(ctx.tenant_id) as s:
        return [AgentOut.of(a) for a in (await s.execute(select(Agent).order_by(Agent.name))).scalars()]


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: uuid.UUID, ctx: TenantContext = Depends(require_role(Role.viewer))) -> AgentOut:
    async with tenant_session(ctx.tenant_id) as s:
        a = await s.get(Agent, agent_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
        return AgentOut.of(a)


@router.post("/agents", response_model=AgentOut, status_code=201)
async def create_agent(body: AgentIn, ctx: TenantContext = Depends(require_role(Role.admin))) -> AgentOut:
    async with tenant_session(ctx.tenant_id) as s:
        a = Agent(
            tenant_id=ctx.tenant_id,
            **body.model_dump(exclude={"model"}),
            model=body.model or "claude-opus-5-5",
            enabled=True,
        )
        s.add(a)
        await s.flush()
        await s.refresh(a)
        await record_audit(s, ctx, "agent.created", "agent", a.id, after={"name": a.name, "role": a.role.value})
        return AgentOut.of(a)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID, body: AgentPatch, ctx: TenantContext = Depends(require_role(Role.admin))
) -> AgentOut:
    changes = body.model_dump(exclude_none=True)
    async with tenant_session(ctx.tenant_id) as s:
        a = await s.get(Agent, agent_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
        before = {k: str(getattr(a, k)) for k in changes}
        for k, v in changes.items():
            setattr(a, k, v)
        await record_audit(s, ctx, "agent.updated", "agent", a.id, before, {k: str(v) for k, v in changes.items()})
        await s.flush()
        await s.refresh(a)
        return AgentOut.of(a)


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[ToolOut]:
    return [
        ToolOut(
            name=t.name,
            description=t.description,
            risk=t.risk.value,
            side_effect=t.side_effect,
            connector=t.connector.value if t.connector else None,
        )
        for t in default_registry().all_specs()
        if not t.is_control
    ]


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(
    subject_key: str | None = None, limit: int = 200, ctx: TenantContext = Depends(require_role(Role.viewer))
) -> list[MemoryOut]:
    q = select(Memory).order_by(Memory.created_at.desc()).limit(min(limit, 500))
    if subject_key:
        q = q.where(Memory.subject_key == subject_key)
    async with tenant_session(ctx.tenant_id) as s:
        return [
            MemoryOut(
                id=m.id,
                scope=m.scope.value,
                subject_key=m.subject_key,
                content=m.content,
                source_run_id=m.source_run_id,
                created_at=m.created_at,
            )
            for m in (await s.execute(q)).scalars()
        ]


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: uuid.UUID, ctx: TenantContext = Depends(require_role(Role.admin))) -> Response:
    async with tenant_session(ctx.tenant_id) as s:
        gone = (await s.execute(delete(Memory).where(Memory.id == memory_id).returning(Memory.content))).first()
        if not gone:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
        await record_audit(s, ctx, "memory.deleted", "memory", memory_id, before={"content": gone[0]})
    return Response(status_code=204)
