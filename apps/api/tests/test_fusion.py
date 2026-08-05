import pytest

from api.fusion import reciprocal_rank_fusion


def ids(result: list[tuple[int, float]]) -> list[int]:
    return [item_id for item_id, _ in result]


def test_empty_input_gives_empty_output() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_single_ranking_preserves_order() -> None:
    assert ids(reciprocal_rank_fusion([[10, 20, 30]])) == [10, 20, 30]


def test_document_in_both_rankings_beats_single_ranking_leaders() -> None:
    vector = [1, 2, 3]
    lexical = [4, 2, 5]

    result = reciprocal_rank_fusion([vector, lexical])

    assert ids(result)[0] == 2  # rank 2 twice beats every single rank-1 appearance


def test_scores_are_sum_of_reciprocal_ranks() -> None:
    result = dict(reciprocal_rank_fusion([[7], [7]], k=60))
    assert result[7] == pytest.approx(2 / 61)


def test_ties_break_deterministically_by_id() -> None:
    result = ids(reciprocal_rank_fusion([[9], [3]]))  # both rank 1 in one ranking
    assert result == [3, 9]


def test_missing_from_one_ranking_contributes_nothing() -> None:
    result = dict(reciprocal_rank_fusion([[1, 2], [2]]))
    assert result[1] == pytest.approx(1 / 61)
    assert result[2] == pytest.approx(1 / 62 + 1 / 61)


def test_smaller_k_amplifies_top_ranks() -> None:
    with_small_k = dict(reciprocal_rank_fusion([[1, 2]], k=1))
    assert with_small_k[1] / with_small_k[2] == pytest.approx((1 / 2) / (1 / 3))


def test_invalid_k_is_rejected() -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[1]], k=0)
