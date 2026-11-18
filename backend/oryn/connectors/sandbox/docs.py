import re

from sqlalchemy import select

from oryn.connectors.base import DocHit
from oryn.connectors.sandbox._common import SandboxBase
from oryn.models import SbDocument

_STOP = {"the", "a", "an", "is", "are", "what", "your", "my", "of", "to", "do", "you", "for", "and", "in", "how", "i"}


def _terms(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOP and len(w) > 1}


class SandboxDocs(SandboxBase):
    async def search(self, query: str, k: int = 3) -> list[DocHit]:
        await self.faults.maybe_fail("docs.search")
        q = _terms(query)
        docs = (await self.s.execute(select(SbDocument))).scalars().all()
        scored: list[DocHit] = []
        for d in docs:
            title_t, body_t = _terms(d.title), _terms(d.body)
            score = 2.0 * len(q & title_t) + len(q & body_t)
            if score > 0:
                scored.append(DocHit(id=d.id, title=d.title, snippet=d.body[:280], score=score))
        scored.sort(key=lambda h: -h.score)
        return scored[:k]
