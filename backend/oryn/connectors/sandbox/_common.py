import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oryn.connectors.faults import FaultInjector
from oryn.models import SbActionLog


class SandboxBase:
    provider = "sandbox"

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, faults: FaultInjector) -> None:
        self.s = session
        self.tenant_id = tenant_id
        self.faults = faults

    async def _replay(self, idempotency_key: str) -> dict[str, Any] | None:
        row = (
            await self.s.execute(select(SbActionLog).where(SbActionLog.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        return row.result if row else None

    async def _record(self, tool: str, idempotency_key: str, result: dict[str, Any]) -> None:
        self.s.add(SbActionLog(tenant_id=self.tenant_id, tool=tool, idempotency_key=idempotency_key, result=result))
        await self.s.flush()
