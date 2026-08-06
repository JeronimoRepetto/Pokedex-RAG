import pytest

from evals.metrics import ndcg_at_k, recall_at_k, reciprocal_rank, top_1_hit


class TestRecallAtK:
    def test_full_hit_within_k(self) -> None:
        assert recall_at_k([1, 2, 3], [1], k=3) == 1.0

    def test_miss_when_relevant_outside_k(self) -> None:
        assert recall_at_k([2, 3, 1], [1], k=2) == 0.0

    def test_partial_recall_with_multiple_relevant_ids(self) -> None:
        assert recall_at_k([1, 9, 9], [1, 2], k=3) == 0.5

    def test_k_larger_than_retrieved_list_is_safe(self) -> None:
        assert recall_at_k([1], [1], k=50) == 1.0

    def test_empty_retrieved_list_is_a_full_miss(self) -> None:
        assert recall_at_k([], [1], k=5) == 0.0

    def test_duplicate_ids_in_retrieved_do_not_inflate_the_score(self) -> None:
        assert recall_at_k([1, 1, 1], [1, 2], k=3) == 0.5

    def test_empty_relevant_set_raises(self) -> None:
        with pytest.raises(ValueError, match="relevant"):
            recall_at_k([1], [], k=5)


class TestReciprocalRank:
    def test_first_position_hit(self) -> None:
        assert reciprocal_rank([1, 2, 3], [1]) == 1.0

    def test_third_position_hit(self) -> None:
        assert reciprocal_rank([9, 8, 1], [1]) == pytest.approx(1 / 3)

    def test_no_hit_anywhere_is_zero(self) -> None:
        assert reciprocal_rank([9, 8, 7], [1]) == 0.0

    def test_takes_the_earliest_of_several_relevant_ids(self) -> None:
        assert reciprocal_rank([9, 2, 1], [1, 2]) == pytest.approx(1 / 2)

    def test_empty_retrieved_is_zero(self) -> None:
        assert reciprocal_rank([], [1]) == 0.0

    def test_empty_relevant_set_raises(self) -> None:
        with pytest.raises(ValueError, match="relevant"):
            reciprocal_rank([1], [])


class TestTop1Hit:
    def test_first_item_relevant(self) -> None:
        assert top_1_hit([1, 2], [1]) == 1.0

    def test_first_item_not_relevant_even_if_relevant_appears_later(self) -> None:
        assert top_1_hit([2, 1], [1]) == 0.0

    def test_empty_retrieved_is_a_miss(self) -> None:
        assert top_1_hit([], [1]) == 0.0

    def test_differs_from_recall_at_1_with_multiple_relevant_ids(self) -> None:
        # top-1 is a binary hit/miss regardless of how many relevant ids exist —
        # recall@1 would instead give partial credit (1/2 here).
        assert top_1_hit([1, 9], [1, 2]) == 1.0
        assert recall_at_k([1, 9], [1, 2], k=1) == 0.5

    def test_empty_relevant_set_raises(self) -> None:
        with pytest.raises(ValueError, match="relevant"):
            top_1_hit([1], [])


class TestNdcgAtK:
    def test_perfect_ranking_scores_one(self) -> None:
        assert ndcg_at_k([1, 2], [1, 2], k=2) == pytest.approx(1.0)

    def test_relevant_item_ranked_second_scores_less_than_ranked_first(self) -> None:
        # binary relevance: with BOTH slots relevant, order among them doesn't matter
        # (that's test_perfect_ranking_scores_one) — order only matters when the single
        # relevant item moves further down the ranking.
        first = ndcg_at_k([1, 9], [1], k=2)
        second = ndcg_at_k([9, 1], [1], k=2)
        assert first == pytest.approx(1.0)
        assert 0.0 < second < first

    def test_no_relevant_hits_scores_zero(self) -> None:
        assert ndcg_at_k([9, 8], [1], k=2) == 0.0

    def test_relevant_hit_beyond_k_is_ignored(self) -> None:
        assert ndcg_at_k([9, 1], [1], k=1) == 0.0

    def test_single_relevant_item_at_rank_one_is_perfect(self) -> None:
        assert ndcg_at_k([1, 9, 9], [1], k=3) == pytest.approx(1.0)

    def test_k_larger_than_relevant_set_still_normalizes_to_one_for_ideal_order(self) -> None:
        assert ndcg_at_k([1, 2, 9, 9], [1, 2], k=4) == pytest.approx(1.0)

    def test_empty_relevant_set_raises(self) -> None:
        with pytest.raises(ValueError, match="relevant"):
            ndcg_at_k([1], [], k=3)
