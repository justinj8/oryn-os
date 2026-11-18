import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from oryn.models import AuditLog

if TYPE_CHECKING:
    from oryn.api.deps import TenantContext


async def record_audit(
    session: AsyncSession,
    ctx: "TenantContext",
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
        )
    )
