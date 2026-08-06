"""Retrieval metrics as pure functions: (ranked retrieved ids, relevant ids) -> float.

No I/O, no API calls — these operate on ids already fetched by `client.py`. Aggregation
across a whole suite (the "Mean" in MRR, averages for a report) happens at the call
site with `statistics.mean`; these functions are the per-case building blocks.
"""

import math


def _relevant_set(relevant: list[int]) -> set[int]:
    if not relevant:
        raise ValueError("relevant must be non-empty")
    return set(relevant)


def recall_at_k(retrieved: list[int], relevant: list[int], k: int) -> float:
    """Fraction of relevant ids present anywhere in the top k retrieved."""
    relevant_set = _relevant_set(relevant)
    hits = len(set(retrieved[:k]) & relevant_set)
    return hits / len(relevant_set)


def reciprocal_rank(retrieved: list[int], relevant: list[int]) -> float:
    """1/rank of the first relevant hit; 0.0 if none of `retrieved` is relevant."""
    relevant_set = _relevant_set(relevant)
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def top_1_hit(retrieved: list[int], relevant: list[int]) -> float:
    """1.0 if the very first retrieved id is relevant, else 0.0 (Hit@1, not Recall@1)."""
    relevant_set = _relevant_set(relevant)
    if not retrieved:
        return 0.0
    return 1.0 if retrieved[0] in relevant_set else 0.0


def _dcg_at_k(retrieved: list[int], relevant_set: set[int], k: int) -> float:
    # Each relevant id contributes at most once, at its best (earliest) rank — search
    # results are per document, and one entity can have several documents, so the
    # same relevant id can legitimately repeat in `retrieved`. Without deduplication
    # a repeat would double-count and push nDCG above its defined [0, 1] range.
    seen: set[int] = set()
    dcg = 0.0
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant_set and item not in seen:
            dcg += 1.0 / math.log2(rank + 1)
            seen.add(item)
    return dcg


def ndcg_at_k(retrieved: list[int], relevant: list[int], k: int) -> float:
    """Binary-relevance normalized DCG@k (no graded relevance in the golden schema)."""
    relevant_set = _relevant_set(relevant)
    dcg = _dcg_at_k(retrieved, relevant_set, k)
    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0
