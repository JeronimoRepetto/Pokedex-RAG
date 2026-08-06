import pytest

from evals.cases import GoldenCase
from evals.scoring import score_case, score_rag_quality, summarize, summarize_rag_quality


def make_case(limit: int = 5, relevant: list[int] | None = None) -> GoldenCase:
    return GoldenCase(
        case_id="text_retrieval_001",
        suite="text_retrieval",
        input={"query": "what type is bulbasaur", "mode": "hybrid", "limit": limit},
        expected={"relevant_pokemon_ids": relevant or [1]},
        origin="handwritten",
    )


def test_score_uses_the_case_limit_as_k() -> None:
    score = score_case(make_case(limit=2), retrieved_ids=[9, 9, 1])

    assert score.recall_at_k == 0.0  # id 1 is at rank 3, outside k=2
    assert score.reciprocal_rank == pytest.approx(1 / 3)
    assert score.top_1_hit == 0.0
    assert score.retrieved_ids == [9, 9, 1]


def test_score_perfect_hit_at_rank_one() -> None:
    score = score_case(make_case(), retrieved_ids=[1, 9, 9])

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

    score = score_case(case, retrieved_ids=[9, 1, 9])

    assert score.recall_at_k == 1.0  # k defaulted to len(retrieved) == 3


def test_summarize_averages_every_metric_across_cases() -> None:
    hit = score_case(make_case(), retrieved_ids=[1])
    miss = score_case(make_case(), retrieved_ids=[9])

    summary = summarize([hit, miss])

    assert summary["recall_at_k"] == pytest.approx(0.5)
    assert summary["mrr"] == pytest.approx(0.5)
    assert summary["top_1_hit_rate"] == pytest.approx(0.5)
    assert summary["ndcg_at_k"] == pytest.approx(0.5)


def test_summarize_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="no scores"):
        summarize([])


def make_rag_case(**expected_overrides) -> GoldenCase:
    expected = {"status": "answered", "must_contain": ["water"]}
    expected.update(expected_overrides)
    return GoldenCase(
        case_id="rag_quality_001",
        suite="rag_quality",
        input={"question": "what type is squirtle?"},
        expected=expected,
        origin="handwritten",
    )


def test_rag_quality_passes_when_status_and_contains_all_match() -> None:
    response = {"status": "answered", "answer": "Squirtle is a Water type [1].", "citations": []}

    score = score_rag_quality(make_rag_case(), response)

    assert score.status_match == 1.0
    assert score.must_contain_ok == 1.0
    assert score.must_not_contain_ok == 1.0
    assert score.passed == 1.0


def test_rag_quality_fails_on_a_hallucinated_forbidden_word() -> None:
    response = {"status": "answered", "answer": "Squirtle is a Grass type [1].", "citations": []}

    score = score_rag_quality(make_rag_case(must_not_contain=["grass"]), response)

    assert score.must_not_contain_ok == 0.0
    assert score.passed == 0.0


def test_rag_quality_fails_when_a_required_fact_is_missing() -> None:
    response = {"status": "answered", "answer": "Squirtle is very small.", "citations": []}

    score = score_rag_quality(make_rag_case(), response)

    assert score.must_contain_ok == 0.0
    assert score.passed == 0.0


def test_rag_quality_checks_status_for_must_abstain_cases() -> None:
    case = make_rag_case(status="insufficient_evidence", must_contain=[])
    grounded_abstain = {"status": "insufficient_evidence", "answer": None, "citations": []}
    wrongly_answered = {"status": "answered", "answer": "Squirtle loves swimming.", "citations": []}

    assert score_rag_quality(case, grounded_abstain).passed == 1.0
    assert score_rag_quality(case, wrongly_answered).status_match == 0.0


def test_rag_quality_case_insensitive_matching() -> None:
    response = {"status": "answered", "answer": "SQUIRTLE IS A WATER TYPE [1].", "citations": []}

    score = score_rag_quality(make_rag_case(), response)

    assert score.must_contain_ok == 1.0


def test_summarize_rag_quality_averages_every_field() -> None:
    passing = score_rag_quality(
        make_rag_case(), {"status": "answered", "answer": "water", "citations": []}
    )
    failing = score_rag_quality(
        make_rag_case(), {"status": "answered", "answer": "nothing relevant", "citations": []}
    )

    summary = summarize_rag_quality([passing, failing])

    assert summary["status_match_rate"] == pytest.approx(1.0)
    assert summary["must_contain_rate"] == pytest.approx(0.5)
    assert summary["pass_rate"] == pytest.approx(0.5)


def test_summarize_rag_quality_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="no scores"):
        summarize_rag_quality([])
