"""Pokémon-vs-Pokémon comparison (Phase 8).

The default path is 100% deterministic: cards from the database, matchup maths from the
shared type chart (libs/db typechart — the same functions that write the corpus's
matchup documents, so the endpoint and the documents can never disagree). No LLM, no
cost, instant.

Deliberately NO `winner` field anywhere. Base stats plus a type chart do not decide a
battle — movesets, abilities and luck dominate — and a confident "winner" would be an
overclaim by schema, the exact thing this project's groundedness judge exists to catch.
A test asserts the field stays absent.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from api.schemas import PokemonCard
from pokedex_db.typechart import Chart, defensive_profile, matchup

logger = logging.getLogger(__name__)

STAT_TOTAL_KEYS = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")


class ChartLookupProtocol(Protocol):
    def chart(self) -> tuple[Chart, tuple[str, ...]]: ...


class SqlChartLookup:
    """Lazy + cached: the chart is ~180 immutable rows, loaded on first use so startup
    and offline tests stay database-free (SqlPokemonTypeLookup's policy)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._cache: tuple[Chart, tuple[str, ...]] | None = None

    def chart(self) -> tuple[Chart, tuple[str, ...]]:
        if self._cache is None:
            from pokedex_db.typechart import load_chart

            with self._session_factory() as session:
                self._cache = load_chart(session)
        return self._cache


class MatchupUnavailableError(RuntimeError):
    """The type chart is empty — the database predates migration 0007's ingest."""


@dataclass(frozen=True)
class SideAssessment:
    name: str
    best_multiplier: float
    best_types: tuple[str, ...]
    verdict: str  # advantage | disadvantage | neutral
    weak_to: tuple[str, ...]
    immune_to: tuple[str, ...]
    stat_total: int


@dataclass(frozen=True)
class MatchupResult:
    a: PokemonCard
    b: PokemonCard
    a_side: SideAssessment
    b_side: SideAssessment
    type_advantage: str  # "a" | "b" | "none"
    stat_advantage: str  # "a" | "b" | "none"
    notes: tuple[str, ...] = field(default_factory=tuple)
    disclaimer: str = (
        "Type and base-stat comparison only — not a battle simulation. "
        "Type matchups follow the current (Generation VI onward) chart."
    )


def _stat_total(card: PokemonCard) -> int:
    return sum(card.stats.get(key, 0) for key in STAT_TOTAL_KEYS)


def _describe(side_name: str, other_name: str, best: float, types: tuple[str, ...]) -> str:
    pretty = side_name.capitalize()
    if best >= 2.0:
        joined = " and ".join(types)
        return f"{pretty}'s {joined} attacks hit {other_name.capitalize()} for {best:g}x."
    if best == 0.0:
        return f"{pretty}'s attacks do not affect {other_name.capitalize()} at all."
    if best < 1.0:
        return f"{pretty}'s attacks are resisted by {other_name.capitalize()} ({best:g}x at best)."
    return f"{pretty} has no type advantage over {other_name.capitalize()} (1x at best)."


def compute_matchup(
    chart: Chart,
    all_types: tuple[str, ...],
    card_a: PokemonCard,
    card_b: PokemonCard,
) -> MatchupResult:
    types_a = tuple(slot.name for slot in card_a.types)
    types_b = tuple(slot.name for slot in card_b.types)
    side_a, side_b = matchup(
        chart,
        first_name=card_a.name,
        first_types=types_a,
        second_name=card_b.name,
        second_types=types_b,
    )
    profile_a = defensive_profile(chart, types_a, all_types)
    profile_b = defensive_profile(chart, types_b, all_types)

    if side_a.best_multiplier > side_b.best_multiplier:
        type_advantage = "a"
    elif side_b.best_multiplier > side_a.best_multiplier:
        type_advantage = "b"
    else:
        type_advantage = "none"

    total_a, total_b = _stat_total(card_a), _stat_total(card_b)
    if total_a != total_b:
        stat_advantage = "a" if total_a > total_b else "b"
    else:
        # Documented tiebreak: equal base-stat totals fall back to speed, and a full tie
        # is honestly "none" rather than an arbitrary pick.
        speed_a, speed_b = card_a.stats.get("speed", 0), card_b.stats.get("speed", 0)
        stat_advantage = "a" if speed_a > speed_b else "b" if speed_b > speed_a else "none"

    notes = (
        _describe(card_a.name, card_b.name, side_a.best_multiplier, side_a.best_types),
        _describe(card_b.name, card_a.name, side_b.best_multiplier, side_b.best_types),
        f"Base stat totals: {card_a.name.capitalize()} {total_a}, "
        f"{card_b.name.capitalize()} {total_b}.",
    )
    return MatchupResult(
        a=card_a,
        b=card_b,
        a_side=SideAssessment(
            name=card_a.name,
            best_multiplier=side_a.best_multiplier,
            best_types=side_a.best_types,
            verdict=side_a.verdict,
            weak_to=profile_a.quad_weak + profile_a.weak,
            immune_to=profile_a.immune,
            stat_total=total_a,
        ),
        b_side=SideAssessment(
            name=card_b.name,
            best_multiplier=side_b.best_multiplier,
            best_types=side_b.best_types,
            verdict=side_b.verdict,
            weak_to=profile_b.quad_weak + profile_b.weak,
            immune_to=profile_b.immune,
            stat_total=total_b,
        ),
        type_advantage=type_advantage,
        stat_advantage=stat_advantage,
        notes=notes,
    )


class MatchupService:
    def __init__(self, repository, chart_lookup: ChartLookupProtocol) -> None:
        self._repository = repository  # PokemonReadRepository
        self._chart_lookup = chart_lookup

    def compare(self, a: str, b: str) -> MatchupResult | None:
        """None when either Pokémon is unknown (the router's 404)."""
        card_a = self._repository.get_card(a)
        card_b = self._repository.get_card(b)
        if card_a is None or card_b is None:
            return None
        chart, all_types = self._chart_lookup.chart()
        if not chart:
            raise MatchupUnavailableError(
                "The type-effectiveness chart is empty — run `pipeline db upgrade` and "
                "`pipeline ingest` (migration 0007) before using /matchup."
            )
        return compute_matchup(chart, all_types, card_a, card_b)
