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


def score_case(case: GoldenCase, retrieved_ids: list[int]) -> CaseScore:
    """Modality-agnostic: text_retrieval and visual_retrieval both resolve to a ranked
    list of pokemon_ids, and relevance is judged the same way regardless of how the
    ids were retrieved."""
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


@dataclass(frozen=True)
class RagQualityScore:
    case_id: str
    status: str | None
    citation_document_ids: list[str]
    status_match: float
    must_contain_ok: float
    must_not_contain_ok: float
    passed: float


def score_rag_quality(case: GoldenCase, response: dict) -> RagQualityScore:
    """expected: {status, must_contain?, must_not_contain?} — must_contain/
    must_not_contain are case-insensitive substring checks against the answer text.
    An empty list is vacuously satisfied (no requirement to check)."""
    expected_status = case.expected.get("status", "answered")
    actual_status = response.get("status")
    status_match = 1.0 if actual_status == expected_status else 0.0

    answer_lower = (response.get("answer") or "").lower()
    must_contain = case.expected.get("must_contain", [])
    must_not_contain = case.expected.get("must_not_contain", [])
    must_contain_ok = 1.0 if all(s.lower() in answer_lower for s in must_contain) else 0.0
    must_not_contain_ok = 0.0 if any(s.lower() in answer_lower for s in must_not_contain) else 1.0

    passed = 1.0 if (status_match and must_contain_ok and must_not_contain_ok) else 0.0
    return RagQualityScore(
        case_id=case.case_id,
        status=actual_status,
        citation_document_ids=[c["document_id"] for c in response.get("citations", [])],
        status_match=status_match,
        must_contain_ok=must_contain_ok,
        must_not_contain_ok=must_not_contain_ok,
        passed=passed,
    )


def summarize_rag_quality(scores: list[RagQualityScore]) -> dict[str, float]:
    if not scores:
        raise ValueError("no scores to summarize")
    return {
        "status_match_rate": statistics.mean(s.status_match for s in scores),
        "must_contain_rate": statistics.mean(s.must_contain_ok for s in scores),
        "must_not_contain_rate": statistics.mean(s.must_not_contain_ok for s in scores),
        "pass_rate": statistics.mean(s.passed for s in scores),
    }


@dataclass(frozen=True)
class ComparisonScore:
    """One golden case scored for ONE provider inside a `/compare` response."""

    case_id: str
    provider: str
    model: str
    citation_document_ids: list[str]
    status_match: float
    must_contain_ok: float
    must_not_contain_ok: float
    passed: float
    judge_grounded: float | None
    latency_ms: int
    prompt_tokens: int
    output_tokens: int


def score_comparison(case: GoldenCase, candidate: dict) -> ComparisonScore:
    """A candidate carries the same status/answer/citations shape as a /chat response,
    so the golden expectations are scored by exactly the same rules — plus the judge
    verdict and per-candidate cost/latency that only /compare reports."""
    base = score_rag_quality(case, candidate)
    verdict = candidate.get("judge")
    return ComparisonScore(
        case_id=case.case_id,
        provider=candidate.get("provider", ""),
        model=candidate.get("model", ""),
        citation_document_ids=base.citation_document_ids,
        status_match=base.status_match,
        must_contain_ok=base.must_contain_ok,
        must_not_contain_ok=base.must_not_contain_ok,
        passed=base.passed,
        judge_grounded=None if verdict is None else float(bool(verdict.get("grounded"))),
        latency_ms=candidate.get("latency_ms", 0),
        prompt_tokens=candidate.get("prompt_tokens", 0),
        output_tokens=candidate.get("output_tokens", 0),
    )


def summarize_comparison(scores: list[ComparisonScore]) -> dict[str, float]:
    """Judged and unjudged cases coexist (a judge can fail open), so the groundedness
    rate is averaged over the judged subset only and reported alongside its own count
    — averaging `None` as 0 would silently punish a provider for a broken judge."""
    if not scores:
        raise ValueError("no scores to summarize")
    judged = [s.judge_grounded for s in scores if s.judge_grounded is not None]
    summary = {
        "status_match_rate": statistics.mean(s.status_match for s in scores),
        "must_contain_rate": statistics.mean(s.must_contain_ok for s in scores),
        "must_not_contain_rate": statistics.mean(s.must_not_contain_ok for s in scores),
        "pass_rate": statistics.mean(s.passed for s in scores),
        "judged_cases": float(len(judged)),
        "mean_latency_ms": statistics.mean(s.latency_ms for s in scores),
        "total_output_tokens": float(sum(s.output_tokens for s in scores)),
        "total_prompt_tokens": float(sum(s.prompt_tokens for s in scores)),
    }
    if judged:
        summary["judge_grounded_rate"] = statistics.mean(judged)
    return summary
