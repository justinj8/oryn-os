"""Persistent agent memory backed by pgvector. Every query runs inside a tenant session (RLS)."""

import uuid

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from oryn.memory.embeddings import Embedder
from oryn.models import Memory, MemoryScope


class MemoryStore:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder

    async def remember(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        scope: MemoryScope,
        subject_key: str,
        content: str,
        source_run_id: uuid.UUID | None,
    ) -> Memory:
        content = content.strip()
        existing = (
            await session.execute(select(Memory).where(Memory.subject_key == subject_key, Memory.content == content))
        ).scalar_one_or_none()
        if existing:
            return existing
        m = Memory(
            tenant_id=tenant_id,
            scope=scope,
            subject_key=subject_key,
            content=content,
            embedding=self.embedder.embed([content])[0],
            source_run_id=source_run_id,
        )
        session.add(m)
        await session.flush()
        return m

    async def recall(
        self, session: AsyncSession, subjects: list[tuple[MemoryScope, str]], query: str, k: int = 5
    ) -> list[Memory]:
        if not subjects:
            return []
        qv = self.embedder.embed([query])[0]
        cond = or_(*(and_(Memory.scope == sc, Memory.subject_key == key) for sc, key in subjects))
        rows = await session.execute(select(Memory).where(cond).order_by(Memory.embedding.cosine_distance(qv)).limit(k))
        return list(rows.scalars())

    async def forget(self, session: AsyncSession, memory_id: uuid.UUID) -> None:
        await session.execute(delete(Memory).where(Memory.id == memory_id))
