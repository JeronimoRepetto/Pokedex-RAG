import pytest

from evals.cases import GoldenCase
from evals.scoring import score_text_retrieval, summarize


def make_case(limit: int = 5, relevant: list[int] | None = None) -> GoldenCase:
    return GoldenCase(
        case_id="text_retrieval_001",
        suite="text_retrieval",
        input={"query": "what type is bulbasaur", "mode": "hybrid", "limit": limit},
        expected={"relevant_pokemon_ids": relevant or [1]},
        origin="handwritten",
    )


def test_score_uses_the_case_limit_as_k() -> None:
    score = score_text_retrieval(make_case(limit=2), retrieved_ids=[9, 9, 1])

    assert score.recall_at_k == 0.0  # id 1 is at rank 3, outside k=2
    assert score.reciprocal_rank == pytest.approx(1 / 3)
    assert score.top_1_hit == 0.0
    assert score.retrieved_ids == [9, 9, 1]


def test_score_perfect_hit_at_rank_one() -> None:
    score = score_text_retrieval(make_case(), retrieved_ids=[1, 9, 9])

    assert score.recall_at_k == 1.0
    assert score.reciprocal_rank == 1.0
    assert score.top_1_hit == 1.0
    assert score.ndcg_at_k == pytest.approx(1.0)


def test_score_falls_back_to_retrieved_length_when_limit_missing() -> None:
    case = GoldenCase(
        case_id="c1",
        suite="text_retrieval",
        input={"query": "x"},
        expected={"relevant_pokemon_ids": [1]},
        origin="handwritten",
    )

    score = score_text_retrieval(case, retrieved_ids=[9, 1, 9])

    assert score.recall_at_k == 1.0  # k defaulted to len(retrieved) == 3


def test_summarize_averages_every_metric_across_cases() -> None:
    hit = score_text_retrieval(make_case(), retrieved_ids=[1])
    miss = score_text_retrieval(make_case(), retrieved_ids=[9])

    summary = summarize([hit, miss])

    assert summary["recall_at_k"] == pytest.approx(0.5)
    assert summary["mrr"] == pytest.approx(0.5)
    assert summary["top_1_hit_rate"] == pytest.approx(0.5)
    assert summary["ndcg_at_k"] == pytest.approx(0.5)


def test_summarize_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="no scores"):
        summarize([])
