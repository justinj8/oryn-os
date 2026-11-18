"""Embeddings. Offline default: a deterministic feature-hashing embedder (no model download).

It is not semantic in the way a neural embedding is, but word, bigram and character-trigram
overlap is enough for agent memory recall over short facts — and it keeps the pgvector code
path identical to what a real embedding provider would use.
"""

import hashlib
import math
import re
from typing import Protocol

from oryn.models import EMBEDDING_DIM

_STOP = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "is", "are", "be", "can", "we", "i", "my"}


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _stem(w: str) -> str:
    for suf in ("ing", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


class HashingEmbedder:
    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[tuple[str, float]]:
        words = [_stem(w) for w in re.findall(r"[a-z0-9$]+", text.lower()) if w not in _STOP]
        feats: list[tuple[str, float]] = [(f"w:{w}", 1.0) for w in words]
        feats += [(f"b:{a}_{b}", 0.5) for a, b in zip(words, words[1:], strict=False)]
        for w in words:
            padded = f"#{w}#"
            feats += [(f"c:{padded[i : i + 3]}", 0.25) for i in range(len(padded) - 2)]
        return feats

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dim
            for feat, weight in self._features(text):
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
                v[h % self.dim] += weight if (h >> 63) & 1 else -weight
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out
