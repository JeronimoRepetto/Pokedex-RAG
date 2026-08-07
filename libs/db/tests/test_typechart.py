"""Type-effectiveness maths. These assertions encode real Pokémon rules, so they are
written from the game's behaviour, not from the implementation."""

import pytest

from pokedex_db.typechart import (
    best_offense,
    defensive_profile,
    matchup,
    multiplier_against,
    multiplier_for,
)

# A deliberately small slice of the real chart, enough to exercise every rule.
CHART = {
    ("water", "fire"): 2.0,
    ("water", "grass"): 0.5,
    ("water", "water"): 0.5,
    ("grass", "water"): 2.0,
    ("grass", "fire"): 0.5,
    ("grass", "grass"): 0.5,
    ("grass", "poison"): 0.5,
    ("grass", "flying"): 0.5,
    ("fire", "grass"): 2.0,
    ("fire", "water"): 0.5,
    ("flying", "grass"): 2.0,
    ("flying", "bug"): 2.0,
    ("poison", "grass"): 2.0,
    ("ground", "poison"): 2.0,
    ("ground", "flying"): 0.0,
    ("psychic", "poison"): 2.0,
    ("ghost", "normal"): 0.0,
    ("normal", "ghost"): 0.0,
}
ALL_TYPES = [
    "bug",
    "fire",
    "flying",
    "ghost",
    "grass",
    "ground",
    "normal",
    "poison",
    "psychic",
    "water",
]


def test_an_absent_pair_is_neutral() -> None:
    """The whole storage design rests on this: only non-neutral pairs are stored."""
    assert multiplier_for(CHART, "water", "normal") == 1.0


def test_known_pairs_read_back() -> None:
    assert multiplier_for(CHART, "water", "fire") == 2.0
    assert multiplier_for(CHART, "grass", "fire") == 0.5
    assert multiplier_for(CHART, "ghost", "normal") == 0.0


def test_dual_types_multiply_to_four_times() -> None:
    """Flying hits grass 2x and bug 2x, so a grass/bug defender takes 4x."""
    assert multiplier_against(CHART, "flying", ["grass", "bug"]) == 4.0


def test_dual_types_can_cancel_to_neutral() -> None:
    """Fire is 2x on grass and 0.5x on water: a grass/water defender takes 1x."""
    assert multiplier_against(CHART, "fire", ["grass", "water"]) == 1.0


def test_an_immunity_in_either_slot_zeroes_the_product() -> None:
    """Ground is 2x on poison but 0x on flying — a poison/flying defender is immune.
    This is why the maths multiplies instead of taking the strongest relation."""
    assert multiplier_against(CHART, "ground", ["poison", "flying"]) == 0.0


def test_bulbasaur_is_doubly_weak_to_flying_but_resists_water() -> None:
    """Grass/poison: flying is 2x on grass and neutral on poison."""
    assert multiplier_against(CHART, "flying", ["grass", "poison"]) == 2.0
    assert multiplier_against(CHART, "water", ["grass", "poison"]) == 0.5


def test_a_single_type_defender_behaves_like_one_multiplier() -> None:
    assert multiplier_against(CHART, "grass", ["water"]) == 2.0


# --- defensive profile ------------------------------------------------------------


def test_profile_buckets_every_multiplier() -> None:
    profile = defensive_profile(CHART, ["grass", "poison"], ALL_TYPES)

    assert profile.defending_types == ("grass", "poison")
    assert "flying" in profile.weak
    assert "fire" in profile.weak
    assert "psychic" in profile.weak
    assert "water" in profile.resists
    assert "grass" in profile.quad_resists  # 0.5 on grass * 0.5 on poison


def test_profile_omits_neutral_types_but_considers_all_of_them() -> None:
    profile = defensive_profile(CHART, ["water"], ALL_TYPES)
    bucketed = set(profile.weak + profile.resists + profile.quad_weak + profile.quad_resists)

    assert "normal" not in bucketed  # neutral, correctly absent
    assert "grass" in profile.weak


def test_profile_reports_immunities() -> None:
    profile = defensive_profile(CHART, ["ghost"], ALL_TYPES)

    assert "normal" in profile.immune


# --- offense and head-to-head -----------------------------------------------------


def test_best_offense_uses_only_the_attackers_own_types() -> None:
    """Bulbasaur (grass/poison) against Squirtle (water): grass is 2x, poison neutral."""
    best, movers = best_offense(CHART, ["grass", "poison"], ["water"])

    assert best == 2.0
    assert movers == ("grass",)


def test_best_offense_reports_every_type_that_ties() -> None:
    """Flying and poison are both 2x on grass, so both are credited — the caller can
    then say "its flying and poison moves both hit hard" rather than picking one."""
    best, movers = best_offense(CHART, ["flying", "poison"], ["grass"])

    assert best == 2.0
    assert movers == ("flying", "poison")


def test_best_offense_ignores_the_attackers_weaker_type() -> None:
    """Grass is 0.5x on grass while poison is 2x: only the winner is reported."""
    best, movers = best_offense(CHART, ["grass", "poison"], ["grass"])

    assert best == 2.0
    assert movers == ("poison",)


def test_best_offense_with_no_types_is_neutral() -> None:
    assert best_offense(CHART, [], ["water"]) == (1.0, ())


def test_matchup_is_not_symmetric() -> None:
    """The headline case: Bulbasaur beats Squirtle offensively AND resists it."""
    bulbasaur, squirtle = matchup(
        CHART,
        first_name="bulbasaur",
        first_types=["grass", "poison"],
        second_name="squirtle",
        second_types=["water"],
    )

    assert bulbasaur.best_multiplier == 2.0
    assert bulbasaur.verdict == "advantage"
    assert bulbasaur.best_types == ("grass",)
    assert squirtle.best_multiplier == 0.5
    assert squirtle.verdict == "disadvantage"


def test_matchup_can_be_neutral_both_ways() -> None:
    first, second = matchup(
        CHART,
        first_name="a",
        first_types=["normal"],
        second_name="b",
        second_types=["psychic"],
    )

    assert (first.verdict, second.verdict) == ("neutral", "neutral")


@pytest.mark.parametrize(
    "multiplier,expected",
    [
        (2.0, "advantage"),
        (4.0, "advantage"),
        (0.5, "disadvantage"),
        (0.0, "disadvantage"),
        (1.0, "neutral"),
    ],
)
def test_verdict_thresholds(multiplier, expected) -> None:
    from pokedex_db.typechart import MatchupSide

    assert MatchupSide("a", "b", multiplier, ()).verdict == expected
