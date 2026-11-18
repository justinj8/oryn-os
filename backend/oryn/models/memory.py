import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from oryn.models.base import Base, TenantScoped, str_enum
from oryn.models.enums import MemoryScope

EMBEDDING_DIM = 384


class Memory(Base, TenantScoped):
    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "ix_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    scope: Mapped[MemoryScope] = mapped_column(str_enum(MemoryScope))
    subject_key: Mapped[str] = mapped_column(String(200), index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    source_run_id: Mapped[uuid.UUID | None]
