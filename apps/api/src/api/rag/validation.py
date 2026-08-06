"""Deterministic post-generation validation: cross-check type claims in the answer
against real DB data for the cited Pokémon (Phase 5.4).

Only checks type claims for now (stats/evolutions are open follow-ups) and only when
exactly one Pokémon is cited — ambiguous which Pokémon a claim refers to otherwise.
A mismatch is "fixed" by appending a correction note, never by rewriting the model's
prose in place: splicing text is what actually breaks grammar/meaning silently.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.rag.context import ContextDocument
from pokedex_db.models import PokemonType, Type


@dataclass(frozen=True)
class TypeCorrection:
    pokemon_name: str
    claimed_types: list[str]
    actual_types: list[str]

    def note(self) -> str:
        claimed = "/".join(self.claimed_types)
        actual = "/".join(self.actual_types)
        return f"Correction: {self.pokemon_name} is {actual} type, not {claimed}."


class PokemonTypeLookupProtocol(Protocol):
    known_types: list[str]

    def types_for(self, pokemon_id: int) -> list[str] | None: ...


def _type_claim_pattern(known_types: list[str]) -> re.Pattern[str]:
    alternation = "|".join(re.escape(t) for t in known_types)
    # "type" can trail with a space ("Water type") or a hyphen and no space
    # ("Water-type", "Grass/Poison-type" — both real model phrasings, caught live).
    return re.compile(
        rf"\b({alternation})(?:[\s,/]+(?:and\s+)?({alternation}))?[\s-]+type\b",
        re.IGNORECASE,
    )


def check_type_claims(
    answer: str,
    citation_map: dict[int, ContextDocument],
    type_lookup: PokemonTypeLookupProtocol,
) -> list[TypeCorrection]:
    known_types = type_lookup.known_types
    if not known_types or not answer:
        return []
    pokemon_ids = {doc.pokemon_id for doc in citation_map.values()}
    if len(pokemon_ids) != 1:
        return []  # ambiguous which Pokémon a bare type claim refers to
    (pokemon_id,) = pokemon_ids
    actual = type_lookup.types_for(pokemon_id)
    if not actual:
        return []
    match = _type_claim_pattern(known_types).search(answer)
    if not match:
        return []
    claimed = [g.lower() for g in match.groups() if g]
    if set(claimed) == {t.lower() for t in actual}:
        return []
    pokemon_name = next(iter(citation_map.values())).pokemon_name
    return [TypeCorrection(pokemon_name=pokemon_name, claimed_types=claimed, actual_types=actual)]


class SqlPokemonTypeLookup:
    """Both queries are lazy + cached: nothing touches the DB until a graph run
    actually reaches the validate node, matching the rest of RagDeps' credential/
    DB-free-until-first-use policy (app startup and offline tests never pay for this)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._known_types_cache: list[str] | None = None

    @property
    def known_types(self) -> list[str]:
        if self._known_types_cache is None:
            with self._session_factory() as session:
                self._known_types_cache = list(session.scalars(select(Type.name)))
        return self._known_types_cache

    def types_for(self, pokemon_id: int) -> list[str] | None:
        with self._session_factory() as session:
            rows = session.execute(
                select(Type.name)
                .join(PokemonType, PokemonType.type_id == Type.id)
                .where(PokemonType.pokemon_id == pokemon_id)
                .order_by(PokemonType.slot)
            ).all()
        return [row[0] for row in rows] or None
