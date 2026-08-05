"""Read repositories. The router depends on the Protocol; the SQL implementation is
bound at app startup and an in-memory fake serves the unit tests."""

from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from api.schemas import (
    AbilityEntry,
    EvolutionChainResponse,
    EvolutionEdge,
    PokemonCard,
    PokemonSummary,
    SpeciesRef,
    TypeSlot,
)
from pokedex_db.models import (
    Ability,
    Evolution,
    FlavorText,
    Pokemon,
    PokemonAbility,
    PokemonStat,
    PokemonType,
    Species,
    Sprite,
    Type,
)


class PokemonReadRepository(Protocol):
    def list_pokemon(
        self, *, page: int, page_size: int, type_name: str | None, name_contains: str | None
    ) -> tuple[list[PokemonSummary], int]: ...

    def get_card(self, id_or_name: str) -> PokemonCard | None: ...

    def get_evolution_chain(self, id_or_name: str) -> EvolutionChainResponse | None: ...


def _resolve_clause(id_or_name: str):
    if id_or_name.isdigit():
        return Pokemon.id == int(id_or_name)
    return Pokemon.name == id_or_name.lower()


class SqlPokemonRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_pokemon(
        self, *, page: int, page_size: int, type_name: str | None, name_contains: str | None
    ) -> tuple[list[PokemonSummary], int]:
        with self._session_factory() as session:
            query = select(Pokemon)
            if name_contains:
                query = query.where(Pokemon.name.contains(name_contains.lower()))
            if type_name:
                query = query.where(
                    Pokemon.id.in_(
                        select(PokemonType.pokemon_id)
                        .join(Type, Type.id == PokemonType.type_id)
                        .where(Type.name == type_name.lower())
                    )
                )
            total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            rows = session.scalars(
                query.order_by(Pokemon.id).offset((page - 1) * page_size).limit(page_size)
            ).all()
            return [self._summary(session, row) for row in rows], total

    def get_card(self, id_or_name: str) -> PokemonCard | None:
        with self._session_factory() as session:
            pokemon = session.scalar(select(Pokemon).where(_resolve_clause(id_or_name)))
            if pokemon is None:
                return None
            species = session.get(Species, pokemon.species_id)
            abilities = session.execute(
                select(Ability.name, PokemonAbility.is_hidden)
                .join(PokemonAbility, PokemonAbility.ability_id == Ability.id)
                .where(PokemonAbility.pokemon_id == pokemon.id)
                .order_by(PokemonAbility.slot)
            ).all()
            stats = session.execute(
                select(PokemonStat.stat_name, PokemonStat.base_value).where(
                    PokemonStat.pokemon_id == pokemon.id
                )
            ).all()
            flavor = session.scalar(
                select(FlavorText.text)
                .where(FlavorText.species_id == species.id)
                .order_by(FlavorText.id)
                .limit(1)
            )
            sprite_kinds = sorted(
                session.scalars(select(Sprite.kind).where(Sprite.pokemon_id == pokemon.id)).all()
            )
            return PokemonCard(
                id=pokemon.id,
                name=pokemon.name,
                generation=species.generation,
                color=species.color,
                habitat=species.habitat,
                is_legendary=species.is_legendary,
                is_mythical=species.is_mythical,
                height_decimetres=pokemon.height,
                weight_hectograms=pokemon.weight,
                base_experience=pokemon.base_experience,
                types=self._type_slots(session, pokemon.id),
                abilities=[AbilityEntry(name=name, is_hidden=hidden) for name, hidden in abilities],
                stats={name: value for name, value in stats},
                flavor_text=flavor,
                sprite_kinds=sprite_kinds,
            )

    def get_evolution_chain(self, id_or_name: str) -> EvolutionChainResponse | None:
        with self._session_factory() as session:
            pokemon = session.scalar(select(Pokemon).where(_resolve_clause(id_or_name)))
            if pokemon is None:
                return None
            species = session.get(Species, pokemon.species_id)
            if species.evolution_chain_id is None:
                return EvolutionChainResponse(chain_id=None, edges=[])
            edges = session.scalars(
                select(Evolution)
                .where(Evolution.chain_id == species.evolution_chain_id)
                .order_by(Evolution.id)
            ).all()
            names = {
                row.id: row.name
                for row in session.scalars(
                    select(Species).where(
                        Species.id.in_(
                            {e.from_species_id for e in edges} | {e.to_species_id for e in edges}
                        )
                    )
                )
            }
            return EvolutionChainResponse(
                chain_id=species.evolution_chain_id,
                edges=[
                    EvolutionEdge(
                        from_species=SpeciesRef(
                            id=e.from_species_id, name=names[e.from_species_id]
                        ),
                        to_species=SpeciesRef(id=e.to_species_id, name=names[e.to_species_id]),
                        trigger=e.trigger,
                        min_level=e.min_level,
                        item=e.item,
                    )
                    for e in edges
                ],
            )

    def _summary(self, session: Session, pokemon: Pokemon) -> PokemonSummary:
        return PokemonSummary(
            id=pokemon.id, name=pokemon.name, types=self._type_slots(session, pokemon.id)
        )

    @staticmethod
    def _type_slots(session: Session, pokemon_id: int) -> list[TypeSlot]:
        rows = session.execute(
            select(PokemonType.slot, Type.name)
            .join(Type, Type.id == PokemonType.type_id)
            .where(PokemonType.pokemon_id == pokemon_id)
            .order_by(PokemonType.slot)
        ).all()
        return [TypeSlot(slot=slot, name=name) for slot, name in rows]
