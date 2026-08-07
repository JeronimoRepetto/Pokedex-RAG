"""Type-effectiveness maths.

Pure functions over a `{(attacking, defending): multiplier}` chart, so the real Pokémon
rules are testable without a database and shared by the pipeline (which writes matchup
documents) and the API (which answers comparisons). Both read the same chart, so a
document and an endpoint can never disagree.

The one rule worth stating out loud: a pair ABSENT from the chart is neutral (1x). Only
non-neutral relations are stored (see `TypeEffectiveness`).
"""

from collections.abc import Iterable
from dataclasses import dataclass

NEUTRAL = 1.0

# PokéAPI's damage_relations keys and the multiplier each implies.
#
# BOTH directions must be imported, even though that writes most pairs twice (harmlessly
# — same key, same value, merged). The `*_from` half is not redundant: a type with no
# snapshot of its own still appears in other types' `*_from` lists. Dark is exactly that
# case here — no Gen-1 Pokémon is Dark, so `type/17` was never fetched, and importing
# only `*_to` would silently claim Dark attacks are neutral against Psychic.
OFFENSIVE_RELATIONS: dict[str, float] = {  # payload type ATTACKS the referenced type
    "double_damage_to": 2.0,
    "half_damage_to": 0.5,
    "no_damage_to": 0.0,
}
DEFENSIVE_RELATIONS: dict[str, float] = {  # referenced type ATTACKS the payload type
    "double_damage_from": 2.0,
    "half_damage_from": 0.5,
    "no_damage_from": 0.0,
}

Chart = dict[tuple[str, str], float]


def multiplier_for(chart: Chart, attacking: str, defending: str) -> float:
    """Single attacking type vs a single defending type. Absent pair = neutral."""
    return chart.get((attacking, defending), NEUTRAL)


def multiplier_against(chart: Chart, attacking: str, defending_types: Iterable[str]) -> float:
    """Attacking type vs a (possibly dual-type) defender.

    Multipliers stack: a Flying attack on Bulbasaur (grass/poison) is 2x on grass and 1x
    on poison -> 2x. On a grass/bug defender it would be 2x * 2x = 4x. An immunity in
    either slot zeroes the whole product, which is why this multiplies rather than taking
    a maximum.
    """
    total = NEUTRAL
    for defending in defending_types:
        total *= multiplier_for(chart, attacking, defending)
    return total


@dataclass(frozen=True)
class DefensiveProfile:
    """How every attacking type fares against one Pokémon's type combination."""

    defending_types: tuple[str, ...]
    quad_weak: tuple[str, ...] = ()  # 4x
    weak: tuple[str, ...] = ()  # 2x
    resists: tuple[str, ...] = ()  # 0.5x
    quad_resists: tuple[str, ...] = ()  # 0.25x
    immune: tuple[str, ...] = ()  # 0x


def defensive_profile(
    chart: Chart, defending_types: Iterable[str], all_types: Iterable[str]
) -> DefensiveProfile:
    """Bucket every attacking type by how it fares against this defender.

    `all_types` must be the full roster: a type that appears in no relation at all is
    still neutral against this defender and must not be silently dropped.
    """
    defending = tuple(defending_types)
    buckets: dict[float, list[str]] = {}
    for attacking in sorted(all_types):
        multiplier = multiplier_against(chart, attacking, defending)
        if multiplier != NEUTRAL:
            buckets.setdefault(multiplier, []).append(attacking)
    return DefensiveProfile(
        defending_types=defending,
        quad_weak=tuple(buckets.get(4.0, [])),
        weak=tuple(buckets.get(2.0, [])),
        resists=tuple(buckets.get(0.5, [])),
        quad_resists=tuple(buckets.get(0.25, [])),
        immune=tuple(buckets.get(0.0, [])),
    )


@dataclass(frozen=True)
class MatchupSide:
    """One direction of a matchup: `attacker`'s best shot at `defender`."""

    attacker: str
    defender: str
    best_multiplier: float
    best_types: tuple[str, ...]

    @property
    def verdict(self) -> str:
        if self.best_multiplier > NEUTRAL:
            return "advantage"
        if self.best_multiplier < NEUTRAL:
            return "disadvantage"
        return "neutral"


def best_offense(
    chart: Chart, attacking_types: Iterable[str], defending_types: Iterable[str]
) -> tuple[float, tuple[str, ...]]:
    """The strongest multiplier the attacker's OWN types achieve against the defender.

    A Pokémon can only use what it has: this considers its own type(s) as attack types,
    not the whole roster. Returns the best multiplier and every type that reaches it.
    """
    defending = tuple(defending_types)
    scored = [
        (attacking, multiplier_against(chart, attacking, defending))
        for attacking in attacking_types
    ]
    if not scored:
        return NEUTRAL, ()
    best = max(multiplier for _, multiplier in scored)
    return best, tuple(sorted(name for name, multiplier in scored if multiplier == best))


def load_chart(session) -> tuple[Chart, tuple[str, ...]]:
    """Read the stored chart and the full type roster from the database.

    The only database-aware function here, kept in this module so every reader — the
    pipeline writing matchup documents and the API answering comparisons — gets the
    chart the same way and cannot drift apart. Returns (chart, all_type_names).
    """
    from sqlalchemy import select

    from pokedex_db.models import Type, TypeEffectiveness

    names = dict(session.execute(select(Type.id, Type.name)).all())
    chart: Chart = {
        (names[attacking], names[defending]): multiplier
        for attacking, defending, multiplier in session.execute(
            select(
                TypeEffectiveness.attacking_type_id,
                TypeEffectiveness.defending_type_id,
                TypeEffectiveness.multiplier,
            )
        ).all()
        if attacking in names and defending in names
    }
    return chart, tuple(sorted(names.values()))


def matchup(
    chart: Chart,
    *,
    first_name: str,
    first_types: Iterable[str],
    second_name: str,
    second_types: Iterable[str],
) -> tuple[MatchupSide, MatchupSide]:
    """Both directions of a head-to-head. Type advantage is not symmetric, so both are
    computed and returned rather than inferring one from the other."""
    first_types, second_types = tuple(first_types), tuple(second_types)
    first_best, first_moves = best_offense(chart, first_types, second_types)
    second_best, second_moves = best_offense(chart, second_types, first_types)
    return (
        MatchupSide(first_name, second_name, first_best, first_moves),
        MatchupSide(second_name, first_name, second_best, second_moves),
    )
