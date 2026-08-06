"""Glue between a golden case + its raw API result and the pure metrics in metrics.py."""

import statistics
from dataclasses import dataclass

from evals import metrics
from evals.cases import GoldenCase


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    retrieved_ids: list[int]
    recall_at_k: float
    reciprocal_rank: float
    top_1_hit: float
    ndcg_at_k: float


def score_text_retrieval(case: GoldenCase, retrieved_ids: list[int]) -> CaseScore:
    relevant = case.expected["relevant_pokemon_ids"]
    k = case.input.get("limit") or len(retrieved_ids) or 1
    return CaseScore(
        case_id=case.case_id,
        retrieved_ids=retrieved_ids,
        recall_at_k=metrics.recall_at_k(retrieved_ids, relevant, k=k),
        reciprocal_rank=metrics.reciprocal_rank(retrieved_ids, relevant),
        top_1_hit=metrics.top_1_hit(retrieved_ids, relevant),
        ndcg_at_k=metrics.ndcg_at_k(retrieved_ids, relevant, k=k),
    )


def summarize(scores: list[CaseScore]) -> dict[str, float]:
    if not scores:
        raise ValueError("no scores to summarize")
    return {
        "recall_at_k": statistics.mean(s.recall_at_k for s in scores),
        "mrr": statistics.mean(s.reciprocal_rank for s in scores),
        "top_1_hit_rate": statistics.mean(s.top_1_hit for s in scores),
        "ndcg_at_k": statistics.mean(s.ndcg_at_k for s in scores),
    }
