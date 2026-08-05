"""Reciprocal Rank Fusion — the pure function that merges vector and lexical rankings.

score(d) = Σ over rankings r of 1 / (k + rank_r(d)); documents missing from a ranking
simply contribute nothing. k=60 is the standard damping constant from the original
RRF paper; ties break by ascending id for determinism.
"""

RRF_K = 60


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
