"""Normalize raw PokéAPI snapshots into domain rows.

Deterministic and idempotent: re-normalizing the same snapshot always converges to the
same rows (entity rows are merged by PokéAPI id; child collections are replaced
wholesale, which is safe because snapshots are immutable).

Referenced entities (types/abilities/moves seen inside a pokemon payload) get minimal
stub rows so foreign keys hold; the full resource payloads enrich them when normalized.
Species MUST be normalized before their pokemon — the normalizer fails fast otherwise.
"""

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pokedex_db.models import (
    Ability,
    Evolution,
    FlavorText,
    Move,
    Pokemon,
    PokemonAbility,
    PokemonMove,
    PokemonStat,
    PokemonType,
    Species,
    Sprite,
    Type,
)

logger = logging.getLogger(__name__)

FLAVOR_LANGUAGE = "en"


class NormalizationError(RuntimeError):
    """A snapshot cannot be normalized (bad payload or missing dependency)."""


def extract_id(url: str) -> int:
    """PokéAPI reference URLs end in /<id>/ — that id is our primary key."""
    try:
        return int(url.rstrip("/").rsplit("/", 1)[-1])
    except ValueError as exc:
        raise NormalizationError(f"Cannot extract a numeric id from URL: {url!r}") from exc


def _generation_number(name: str) -> int:
    romans = {
        "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
        "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    }  # fmt: skip
    suffix = name.removeprefix("generation-")
    if suffix not in romans:
        raise NormalizationError(f"Unknown generation name: {name!r}")
    return romans[suffix]


def _stub_type(session: Session, ref: dict[str, Any]) -> int:
    type_id = extract_id(ref["url"])
    if session.get(Type, type_id) is None:
        session.add(Type(id=type_id, name=ref["name"]))
    return type_id


def _stub_ability(session: Session, ref: dict[str, Any]) -> int:
    ability_id = extract_id(ref["url"])
    if session.get(Ability, ability_id) is None:
        session.add(Ability(id=ability_id, name=ref["name"]))
    return ability_id


def _stub_move(session: Session, ref: dict[str, Any]) -> int:
    move_id = extract_id(ref["url"])
    if session.get(Move, move_id) is None:
        session.add(Move(id=move_id, name=ref["name"]))
    return move_id


def normalize_species(session: Session, payload: dict[str, Any]) -> None:
    session.merge(
        Species(
            id=payload["id"],
            name=payload["name"],
            generation=_generation_number(payload["generation"]["name"]),
            color=(payload.get("color") or {}).get("name"),
            habitat=(payload.get("habitat") or {}).get("name"),
            capture_rate=payload.get("capture_rate"),
            is_legendary=payload.get("is_legendary", False),
            is_mythical=payload.get("is_mythical", False),
            evolution_chain_id=(
                extract_id(payload["evolution_chain"]["url"])
                if payload.get("evolution_chain")
                else None
            ),
        )
    )
    session.execute(delete(FlavorText).where(FlavorText.species_id == payload["id"]))
    seen: set[tuple[str, str]] = set()
    for entry in payload.get("flavor_text_entries", []):
        language = entry["language"]["name"]
        version = (entry.get("version") or {}).get("name", "unknown")
        if language != FLAVOR_LANGUAGE or (version, language) in seen:
            continue
        seen.add((version, language))
        session.add(
            FlavorText(
                species_id=payload["id"],
                version=version,
                language=language,
                text=entry["flavor_text"].replace("\n", " ").replace("\f", " "),
            )
        )


def normalize_pokemon(session: Session, payload: dict[str, Any]) -> None:
    species_id = extract_id(payload["species"]["url"])
    if session.get(Species, species_id) is None:
        raise NormalizationError(
            f"Species {species_id} not found for pokemon {payload['name']!r} — "
            "normalize pokemon-species snapshots before pokemon."
        )

    pokemon_id = payload["id"]
    session.merge(
        Pokemon(
            id=pokemon_id,
            name=payload["name"],
            species_id=species_id,
            height=payload.get("height"),
            weight=payload.get("weight"),
            base_experience=payload.get("base_experience"),
            is_default=payload.get("is_default", True),
        )
    )

    # Phase 1 — referenced-entity stubs, flushed BEFORE any child row references them.
    # Interleaving session.get() queries with pending child inserts lets query-invoked
    # autoflush write a child row before its stub exists: ForeignKeyViolation on
    # PostgreSQL (invisible on SQLite, which doesn't enforce FKs). Live-ingest bug,
    # 2026-08-05; regression test in tests/test_normalize_integration.py.
    type_ids = {
        entry["slot"]: _stub_type(session, entry["type"]) for entry in payload.get("types", [])
    }
    ability_entries = [
        (entry["slot"], _stub_ability(session, entry["ability"]), entry.get("is_hidden", False))
        for entry in payload.get("abilities", [])
    ]
    move_ids = {
        entry["move"]["name"]: _stub_move(session, entry["move"])
        for entry in payload.get("moves", [])
    }
    session.flush()

    # Phase 2 — replace child collections wholesale.
    session.execute(delete(PokemonType).where(PokemonType.pokemon_id == pokemon_id))
    for slot, type_id in type_ids.items():
        session.add(PokemonType(pokemon_id=pokemon_id, slot=slot, type_id=type_id))

    session.execute(delete(PokemonAbility).where(PokemonAbility.pokemon_id == pokemon_id))
    for slot, ability_id, is_hidden in ability_entries:
        session.add(
            PokemonAbility(
                pokemon_id=pokemon_id, slot=slot, ability_id=ability_id, is_hidden=is_hidden
            )
        )

    session.execute(delete(PokemonStat).where(PokemonStat.pokemon_id == pokemon_id))
    for entry in payload.get("stats", []):
        session.add(
            PokemonStat(
                pokemon_id=pokemon_id,
                stat_name=entry["stat"]["name"],
                base_value=entry["base_stat"],
                effort=entry.get("effort", 0),
            )
        )

    session.execute(delete(PokemonMove).where(PokemonMove.pokemon_id == pokemon_id))
    learned: set[tuple[int, str, int]] = set()
    for entry in payload.get("moves", []):
        move_id = move_ids[entry["move"]["name"]]
        for detail in entry.get("version_group_details", []):
            key = (move_id, detail["move_learn_method"]["name"], detail["level_learned_at"])
            if key in learned:
                continue
            learned.add(key)
            session.add(
                PokemonMove(
                    pokemon_id=pokemon_id,
                    move_id=key[0],
                    learn_method=key[1],
                    level=key[2],
                )
            )

    _upsert_sprites(session, pokemon_id, payload.get("sprites") or {})


def _upsert_sprites(session: Session, pokemon_id: int, sprites: dict[str, Any]) -> None:
    candidates = {
        "default": sprites.get("front_default"),
        "shiny": sprites.get("front_shiny"),
        "official-artwork": ((sprites.get("other") or {}).get("official-artwork") or {}).get(
            "front_default"
        ),
    }
    for kind, url in candidates.items():
        if not url:
            continue
        existing = session.scalar(
            select(Sprite).where(Sprite.pokemon_id == pokemon_id, Sprite.kind == kind)
        )
        if existing is None:
            session.add(Sprite(pokemon_id=pokemon_id, kind=kind, source_url=url))
        elif existing.source_url != url:
            existing.source_url = url  # re-download picked up by the sprite job


def normalize_evolution_chain(session: Session, payload: dict[str, Any]) -> None:
    """Insert evolution edges for one chain.

    Edges touching species that are not ingested (e.g. a Gen-2 evolution of a Gen-1
    Pokémon, like golbat→crobat) are skipped with a warning — explicit, logged
    degradation while the project only ingests Gen 1.
    """
    chain_id = payload["id"]
    session.execute(delete(Evolution).where(Evolution.chain_id == chain_id))

    def walk(node: dict[str, Any]) -> None:
        from_id = extract_id(node["species"]["url"])
        for child in node.get("evolves_to", []):
            to_id = extract_id(child["species"]["url"])
            if session.get(Species, from_id) is None or session.get(Species, to_id) is None:
                logger.warning(
                    "evolution edge skipped: species not ingested",
                    extra={"chain_id": chain_id, "from": from_id, "to": to_id},
                )
                walk(child)
                continue
            details = child.get("evolution_details", [])
            first = details[0] if details else {}
            session.add(
                Evolution(
                    chain_id=chain_id,
                    from_species_id=from_id,
                    to_species_id=to_id,
                    trigger=(first.get("trigger") or {}).get("name"),
                    min_level=first.get("min_level"),
                    item=((first.get("item") or {}) or {}).get("name"),
                    conditions={"details": details},
                )
            )
            walk(child)

    walk(payload["chain"])


def _english_effect(payload: dict[str, Any]) -> str | None:
    for entry in payload.get("effect_entries", []):
        if entry["language"]["name"] == FLAVOR_LANGUAGE:
            return entry.get("short_effect") or entry.get("effect")
    return None


def normalize_move(session: Session, payload: dict[str, Any]) -> None:
    type_id = extract_id(payload["type"]["url"]) if payload.get("type") else None
    if type_id is not None and session.get(Type, type_id) is None:
        session.add(Type(id=type_id, name=payload["type"]["name"]))
        session.flush()  # the move row references it (see normalize_pokemon phase note)
    session.merge(
        Move(
            id=payload["id"],
            name=payload["name"],
            type_id=type_id,
            power=payload.get("power"),
            accuracy=payload.get("accuracy"),
            pp=payload.get("pp"),
            damage_class=(payload.get("damage_class") or {}).get("name"),
            effect_text=_english_effect(payload),
        )
    )


def normalize_ability(session: Session, payload: dict[str, Any]) -> None:
    session.merge(
        Ability(id=payload["id"], name=payload["name"], effect_text=_english_effect(payload))
    )


def normalize_type(session: Session, payload: dict[str, Any]) -> None:
    session.merge(Type(id=payload["id"], name=payload["name"]))


# Dependency-safe processing order for `pipeline normalize`.
NORMALIZERS: dict[str, Any] = {
    "type": normalize_type,
    "ability": normalize_ability,
    "move": normalize_move,
    "pokemon-species": normalize_species,
    "pokemon": normalize_pokemon,
    "evolution-chain": normalize_evolution_chain,
}
