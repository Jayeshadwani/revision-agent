"""
PH4-RETRIEVE-001 (issue #9): Reciprocal Rank Fusion.

    RRF_score(d) = sum over retrievers r of 1 / (rrf_k + rank_r(d))      ranks start at 1

Only ranks are used, so dense cosine scores and BM25 scores never need normalising. No per-retriever
weights: the ticket asks for plain RRF until dense-only and hybrid baselines are measured.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RRF_K = 60


@dataclass
class Fused:
    chunk_id: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)      # retriever -> 1-based rank

    @property
    def source(self) -> str:
        return "+".join(sorted(self.ranks))


def rrf(ranked: dict[str, list[str]], k: int = RRF_K) -> list[Fused]:
    """Fuse several ranked lists of chunk IDs (best first). Ties break on the best single rank, then
    on the number of retrievers that found the chunk, then on chunk ID, so the order is stable."""
    if k <= 0:
        raise ValueError("rrf_k must be positive")
    fused: dict[str, Fused] = {}
    for name, ids in ranked.items():
        seen = set()
        for rank, cid in enumerate(ids, 1):
            if cid in seen:                        # a retriever lists each chunk once
                raise ValueError(f"{name} lists {cid} twice")
            seen.add(cid)
            f = fused.setdefault(cid, Fused(cid, 0.0))
            f.score += 1.0 / (k + rank)
            f.ranks[name] = rank
    return sorted(fused.values(), key=lambda f: (-f.score, min(f.ranks.values()), -len(f.ranks), f.chunk_id))
