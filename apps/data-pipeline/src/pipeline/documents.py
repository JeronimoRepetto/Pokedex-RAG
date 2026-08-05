"""Deterministic RAG document builder.

Documents are rendered from domain rows with fixed templates and stable ordering — the
LLM never writes them, so stats/types/evolutions in the corpus are facts by
construction. Re-running the builder converges: unchanged content keeps its hash and
row untouched (the embed job uses that to skip re-embedding).
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pokedex_db.models import (
    Ability,
    Document,
    Evolution,
    FlavorText,
    Move,
    Pokemon,
    PokemonAbility,
    PokemonMove,
    PokemonStat,
    PokemonType,
    Species,
    Type,
)

logger = logging.getLogger(__name__)

POKEAPI_BASE = "https://pokeapi.co/api/v2"

STAT_NAMES = {
    "hp": "HP",
    "attack": "Attack",
    "defense": "Defense",
    "special-attack": "Special Attack",
    "special-defense": "Special Defense",
    "speed": "Speed",
}


@dataclass(frozen=True)
class DocumentDraft:
    doc_type: str
    pokemon_id: int
    title: str
    content: str
    source_refs: dict[str, Any]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def _display(name: str) -> str:
    return name.replace("-", " ").title()


def _evolution_condition(edge: Evolution) -> str:
    if edge.trigger == "level-up" and edge.min_level:
        return f"at level {edge.min_level}"
    if edge.trigger == "use-item" and edge.item:
        return f"using a {_display(edge.item)}"
    if edge.trigger == "trade":
        return "when traded"
    if edge.min_level:
        return f"at level {edge.min_level}"
    return f"via {_display(edge.trigger)}" if edge.trigger else "under special conditions"


class DocumentBuilder:
    def __init__(self, session: Session) -> None:
        self._session = session

    def build_for_pokemon(self, pokemon_id: int) -> list[DocumentDraft]:
        pokemon = self._session.get(Pokemon, pokemon_id)
        if pokemon is None:
            raise ValueError(f"Pokemon {pokemon_id} not found — run ingest first")
        species = self._session.get(Species, pokemon.species_id)
        drafts = [
            self._card(pokemon, species),
            self._flavor(pokemon, species),
            self._moves(pokemon),
            self._evolution(pokemon, species),
        ]
        return [d for d in drafts if d is not None]

    def upsert(self, drafts: list[DocumentDraft]) -> tuple[int, int, int]:
        """Persist drafts; returns (created, updated, unchanged)."""
        created = updated = unchanged = 0
        for draft in drafts:
            row = self._session.scalar(
                select(Document).where(
                    Document.pokemon_id == draft.pokemon_id,
                    Document.doc_type == draft.doc_type,
                )
            )
            if row is None:
                self._session.add(
                    Document(
                        doc_type=draft.doc_type,
                        pokemon_id=draft.pokemon_id,
                        title=draft.title,
                        content=draft.content,
                        content_hash=draft.content_hash,
                        source_refs=draft.source_refs,
                    )
                )
                created += 1
            elif row.content_hash != draft.content_hash:
                row.title = draft.title
                row.content = draft.content
                row.content_hash = draft.content_hash
                row.source_refs = draft.source_refs
                updated += 1
            else:
                unchanged += 1
        return created, updated, unchanged

    # --- individual documents -------------------------------------------------

    def _card(self, pokemon: Pokemon, species: Species) -> DocumentDraft:
        name = _display(pokemon.name)
        types = self._type_names(pokemon.id)
        lines = [
            f"{name} is a {'/'.join(types)} type Pokémon from generation {species.generation}.",
            f"National Pokédex number: {pokemon.id}.",
        ]
        if pokemon.height is not None and pokemon.weight is not None:
            lines.append(f"Height: {pokemon.height / 10:g} m. Weight: {pokemon.weight / 10:g} kg.")
        traits = []
        if species.color:
            traits.append(f"Color: {species.color}.")
        if species.habitat:
            traits.append(f"Habitat: {species.habitat}.")
        if traits:
            lines.append(" ".join(traits))

        abilities = self._session.execute(
            select(Ability.name, Ability.effect_text, PokemonAbility.is_hidden)
            .join(PokemonAbility, PokemonAbility.ability_id == Ability.id)
            .where(PokemonAbility.pokemon_id == pokemon.id)
            .order_by(PokemonAbility.slot)
        ).all()
        if abilities:
            rendered = []
            for ability_name, effect, hidden in abilities:
                label = _display(ability_name) + (" (hidden ability)" if hidden else "")
                rendered.append(f"{label}: {effect}" if effect else label)
            lines.append("Abilities: " + " | ".join(rendered))

        stats = dict(
            self._session.execute(
                select(PokemonStat.stat_name, PokemonStat.base_value).where(
                    PokemonStat.pokemon_id == pokemon.id
                )
            ).all()
        )
        if stats:
            ordered = [f"{label} {stats[key]}" for key, label in STAT_NAMES.items() if key in stats]
            lines.append("Base stats: " + ", ".join(ordered) + ".")
        if species.capture_rate is not None:
            lines.append(f"Capture rate: {species.capture_rate}.")
        if species.is_legendary:
            lines.append(f"{name} is a legendary Pokémon.")
        if species.is_mythical:
            lines.append(f"{name} is a mythical Pokémon.")
        lines.extend(self._evolution_sentences(species))

        return DocumentDraft(
            doc_type="card",
            pokemon_id=pokemon.id,
            title=f"{name} (#{pokemon.id}) — Pokédex card",
            content="\n".join(lines),
            source_refs=self._refs(pokemon, species),
        )

    def _flavor(self, pokemon: Pokemon, species: Species) -> DocumentDraft | None:
        rows = self._session.execute(
            select(FlavorText.text, FlavorText.version)
            .where(FlavorText.species_id == species.id)
            .order_by(FlavorText.id)
        ).all()
        if not rows:
            return None
        by_text: dict[str, list[str]] = {}
        for text_value, version in rows:
            by_text.setdefault(" ".join(text_value.split()), []).append(version)
        name = _display(pokemon.name)
        lines = [
            f"{entry} (versions: {', '.join(versions)})"
            for entry, versions in sorted(by_text.items())
        ]
        return DocumentDraft(
            doc_type="flavor",
            pokemon_id=pokemon.id,
            title=f"{name} — Pokédex entries",
            content="\n".join(lines),
            source_refs=self._refs(pokemon, species),
        )

    def _moves(self, pokemon: Pokemon) -> DocumentDraft | None:
        level_up = self._session.execute(
            select(PokemonMove.level, Move.name, Move.power, Move.accuracy, Type.name)
            .join(Move, Move.id == PokemonMove.move_id)
            .join(Type, Type.id == Move.type_id, isouter=True)
            .where(PokemonMove.pokemon_id == pokemon.id, PokemonMove.learn_method == "level-up")
            .order_by(PokemonMove.level, Move.name)
        ).all()
        other_count = self._session.execute(
            select(PokemonMove.move_id)
            .where(PokemonMove.pokemon_id == pokemon.id, PokemonMove.learn_method != "level-up")
            .distinct()
        ).all()
        if not level_up and not other_count:
            return None
        name = _display(pokemon.name)
        lines = []
        if level_up:
            rendered = []
            seen: set[str] = set()
            for level, move_name, power, accuracy, type_name in level_up:
                if move_name in seen:
                    continue
                seen.add(move_name)
                details = [
                    d
                    for d in (
                        type_name,
                        f"power {power}" if power else None,
                        f"accuracy {accuracy}" if accuracy else None,
                    )
                    if d
                ]
                suffix = f" ({', '.join(details)})" if details else ""
                when = f"at level {level}" if level > 1 else "from the start"
                rendered.append(f"{_display(move_name)}{suffix} {when}")
            lines.append(f"{name} learns by leveling up: " + "; ".join(rendered) + ".")
        if other_count:
            lines.append(
                f"{name} can also learn {len(other_count)} other moves via machines, "
                "tutors, eggs or other methods."
            )
        return DocumentDraft(
            doc_type="moves",
            pokemon_id=pokemon.id,
            title=f"{name} — moves",
            content="\n".join(lines),
            source_refs={
                "pokeapi": [f"{POKEAPI_BASE}/pokemon/{pokemon.id}/"],
            },
        )

    def _evolution(self, pokemon: Pokemon, species: Species) -> DocumentDraft | None:
        sentences = self._evolution_sentences(species, full_chain=True)
        if not sentences:
            return None
        name = _display(pokemon.name)
        return DocumentDraft(
            doc_type="evolution",
            pokemon_id=pokemon.id,
            title=f"{name} — evolution line",
            content="\n".join(sentences),
            source_refs={
                "pokeapi": [
                    f"{POKEAPI_BASE}/pokemon-species/{species.id}/",
                    f"{POKEAPI_BASE}/evolution-chain/{species.evolution_chain_id}/",
                ],
            },
        )

    # --- helpers ----------------------------------------------------------------

    def _type_names(self, pokemon_id: int) -> list[str]:
        return list(
            self._session.scalars(
                select(Type.name)
                .join(PokemonType, PokemonType.type_id == Type.id)
                .where(PokemonType.pokemon_id == pokemon_id)
                .order_by(PokemonType.slot)
            ).all()
        ) or ["unknown"]

    def _evolution_sentences(self, species: Species, full_chain: bool = False) -> list[str]:
        if species.evolution_chain_id is None:
            return []
        edges = self._session.scalars(
            select(Evolution)
            .where(Evolution.chain_id == species.evolution_chain_id)
            .order_by(Evolution.id)
        ).all()
        if not edges:
            return []
        names = {
            row.id: _display(row.name)
            for row in self._session.scalars(
                select(Species).where(
                    Species.id.in_(
                        {e.from_species_id for e in edges} | {e.to_species_id for e in edges}
                    )
                )
            )
        }
        relevant = (
            edges
            if full_chain
            else [e for e in edges if species.id in (e.from_species_id, e.to_species_id)]
        )
        return [
            f"{names[e.from_species_id]} evolves into {names[e.to_species_id]} "
            f"{_evolution_condition(e)}."
            for e in relevant
        ]

    @staticmethod
    def _refs(pokemon: Pokemon, species: Species) -> dict[str, Any]:
        return {
            "pokeapi": [
                f"{POKEAPI_BASE}/pokemon/{pokemon.id}/",
                f"{POKEAPI_BASE}/pokemon-species/{species.id}/",
            ],
        }
