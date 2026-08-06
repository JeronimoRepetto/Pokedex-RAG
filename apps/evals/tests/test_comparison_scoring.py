"""Scoring of /compare candidates: same golden rules as rag_quality, plus the judge
verdict and per-candidate cost/latency."""

import pytest

from evals.cases import GoldenCase
from evals.scoring import ComparisonScore, score_comparison, summarize_comparison


def case(**expected) -> GoldenCase:
    return GoldenCase(
        case_id="rag_quality_001",
        suite="rag_quality",
        input={"question": "what type is bulbasaur?"},
        expected={"status": "answered", **expected},
        origin="handwritten",
    )


def candidate(**overrides) -> dict:
    base = {
        "provider": "vertex-gemini",
        "model": "gemini-3.6-flash",
        "status": "answered",
        "answer": "Bulbasaur is grass/poison [1].",
        "citations": [{"document_id": "1", "marker": 1}],
        "judge": {"grounded": True, "hallucination_detected": False, "reasoning": "ok"},
        "latency_ms": 900,
        "prompt_tokens": 500,
        "output_tokens": 40,
    }
    return {**base, **overrides}


def test_a_passing_candidate_scores_one() -> None:
    score = score_comparison(case(must_contain=["grass"]), candidate())

    assert score.passed == 1.0
    assert score.provider == "vertex-gemini"
    assert score.model == "gemini-3.6-flash"
    assert score.judge_grounded == 1.0
    assert score.latency_ms == 900


def test_must_not_contain_failure_fails_the_case() -> None:
    score = score_comparison(
        case(must_not_contain=["fire"]),
        candidate(answer="Bulbasaur is a fire type [1]."),
    )

    assert score.must_not_contain_ok == 0.0
    assert score.passed == 0.0


def test_an_ungrounded_verdict_is_recorded_without_failing_the_golden_case() -> None:
    """Judge groundedness and golden-case expectations are separate signals: an answer
    can satisfy the expectations while the judge still flags it."""
    score = score_comparison(
        case(must_contain=["grass"]),
        candidate(judge={"grounded": False, "hallucination_detected": True, "reasoning": "x"}),
    )

    assert score.passed == 1.0
    assert score.judge_grounded == 0.0


def test_an_unjudged_candidate_has_no_groundedness() -> None:
    score = score_comparison(case(must_contain=["grass"]), candidate(judge=None))

    assert score.judge_grounded is None


def test_provider_error_candidate_scores_zero() -> None:
    score = score_comparison(
        case(must_contain=["grass"]),
        candidate(status="provider_error", answer=None, judge=None, citations=[]),
    )

    assert score.status_match == 0.0
    assert score.passed == 0.0


def make_score(**overrides) -> ComparisonScore:
    base = {
        "case_id": "c",
        "provider": "p",
        "model": "m",
        "citation_document_ids": [],
        "status_match": 1.0,
        "must_contain_ok": 1.0,
        "must_not_contain_ok": 1.0,
        "passed": 1.0,
        "judge_grounded": 1.0,
        "latency_ms": 1000,
        "prompt_tokens": 100,
        "output_tokens": 10,
    }
    return ComparisonScore(**{**base, **overrides})


def test_summary_aggregates_rates_tokens_and_latency() -> None:
    summary = summarize_comparison([make_score(), make_score(passed=0.0, latency_ms=2000)])

    assert summary["pass_rate"] == 0.5
    assert summary["mean_latency_ms"] == 1500
    assert summary["total_output_tokens"] == 20
    assert summary["total_prompt_tokens"] == 200
    assert summary["judged_cases"] == 2


def test_groundedness_averages_only_the_judged_subset() -> None:
    """An unjudged case must not count as ungrounded — a broken judge would otherwise
    look like a bad provider."""
    summary = summarize_comparison([make_score(), make_score(judge_grounded=None)])

    assert summary["judge_grounded_rate"] == 1.0
    assert summary["judged_cases"] == 1


def test_no_judged_cases_omits_the_groundedness_rate() -> None:
    summary = summarize_comparison([make_score(judge_grounded=None)])

    assert "judge_grounded_rate" not in summary
    assert summary["judged_cases"] == 0


def test_summarizing_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="no scores"):
        summarize_comparison([])
