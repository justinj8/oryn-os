"""Exactly-once guard for real outbound messages (Twilio SMS, SMTP email).

An agent step runs in one transaction that rolls back when Temporal retries the step. If the
"already sent" record lived in that transaction, a rollback would erase it and the retry would
text the customer again. So the delivery record is written in its own, separately committed
transaction, on the short-lived 'spans' pool (never the step pool), right after the provider
accepts the message.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from oryn.core.db import tenant_session
from oryn.models import SbActionLog


def _key(idempotency_key: str) -> str:
    return f"{idempotency_key}:delivered"


async def already_delivered(tenant_id: uuid.UUID, idempotency_key: str) -> bool:
    async with tenant_session(tenant_id, pool="spans") as s:
        row = await s.execute(select(SbActionLog.id).where(SbActionLog.idempotency_key == _key(idempotency_key)))
        return row.first() is not None


async def mark_delivered(tenant_id: uuid.UUID, idempotency_key: str, provider: str) -> None:
    async with tenant_session(tenant_id, pool="spans") as s:
        await s.execute(
            insert(SbActionLog)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                tool=f"delivered:{provider}",
                idempotency_key=_key(idempotency_key),
                result={},
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "idempotency_key"])
        )
