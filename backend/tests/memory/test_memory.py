import math

from oryn.core.db import tenant_session
from oryn.memory.embeddings import HashingEmbedder
from oryn.memory.store import MemoryStore
from oryn.models import MemoryScope
from tests.factories import make_tenant

E = HashingEmbedder()


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_embedder_deterministic_and_normalized() -> None:
    v1, v2 = E.embed(["prefers morning appointments"])[0], E.embed(["prefers morning appointments"])[0]
    assert v1 == v2 and len(v1) == 384
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-6)


def test_similar_text_closer() -> None:
    q, near, far = E.embed(["prefers morning appointments", "likes mornings for appointments", "invoice overdue"])
    assert _cos(q, near) > _cos(q, far)


async def test_recall_filters_by_subject_and_ranks() -> None:
    t = await make_tenant("acme")
    store = MemoryStore(E)
    async with tenant_session(t.id) as s:
        await store.remember(s, t.id, MemoryScope.contact, "contact:dana@x.com", "Prefers morning appointments", None)
        await store.remember(s, t.id, MemoryScope.contact, "contact:dana@x.com", "Budget about $8,000", None)
        await store.remember(s, t.id, MemoryScope.contact, "contact:lee@x.com", "Prefers morning calls", None)
        got = await store.recall(s, [(MemoryScope.contact, "contact:dana@x.com")], "when can we book a morning slot")
    assert [m.content for m in got][0] == "Prefers morning appointments"
    assert all(m.subject_key == "contact:dana@x.com" for m in got)


async def test_duplicate_memory_not_stored_twice() -> None:
    t = await make_tenant("acme")
    store = MemoryStore(E)
    async with tenant_session(t.id) as s:
        a = await store.remember(s, t.id, MemoryScope.contact, "contact:a", "Likes email", None)
        b = await store.remember(s, t.id, MemoryScope.contact, "contact:a", "Likes email", None)
        got = await store.recall(s, [(MemoryScope.contact, "contact:a")], "email", k=10)
    assert a.id == b.id and len(got) == 1


async def test_recall_respects_rls() -> None:
    a, b = await make_tenant("a"), await make_tenant("b")
    store = MemoryStore(E)
    async with tenant_session(b.id) as s:
        await store.remember(s, b.id, MemoryScope.contact, "contact:x", "Secret fact", None)
    async with tenant_session(a.id) as s:
        assert await store.recall(s, [(MemoryScope.contact, "contact:x")], "secret") == []


async def test_forget() -> None:
    t = await make_tenant("acme")
    store = MemoryStore(E)
    async with tenant_session(t.id) as s:
        m = await store.remember(s, t.id, MemoryScope.agent, "agent:sales", "Use friendly tone", None)
        await store.forget(s, m.id)
        assert await store.recall(s, [(MemoryScope.agent, "agent:sales")], "tone") == []
