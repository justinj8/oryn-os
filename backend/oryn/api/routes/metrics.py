from fastapi import APIRouter, Depends, Query

from oryn.api.deps import TenantContext, require_role
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.metrics.service import (
    AgentLeaderboardRow,
    OverviewMetrics,
    TimeseriesPoint,
    agent_leaderboard,
    overview,
    timeseries,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])
Range = Query(30, alias="range", ge=1, le=365)


@router.get("/overview", response_model=OverviewMetrics)
async def get_overview(range_days: int = Range, ctx: TenantContext = Depends(require_role(Role.viewer))):
    async with tenant_session(ctx.tenant_id) as s:
        return await overview(s, range_days)


@router.get("/timeseries", response_model=list[TimeseriesPoint])
async def get_timeseries(range_days: int = Range, ctx: TenantContext = Depends(require_role(Role.viewer))):
    async with tenant_session(ctx.tenant_id) as s:
        return await timeseries(s, range_days)


@router.get("/agents", response_model=list[AgentLeaderboardRow])
async def get_agents(range_days: int = Range, ctx: TenantContext = Depends(require_role(Role.viewer))):
    async with tenant_session(ctx.tenant_id) as s:
        return await agent_leaderboard(s, range_days)
