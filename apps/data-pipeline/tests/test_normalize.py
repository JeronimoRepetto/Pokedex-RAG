import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from pipeline.normalize import (
    NormalizationError,
    extract_id,
    normalize_ability,
    normalize_evolution_chain,
    normalize_move,
    normalize_pokemon,
    normalize_species,
)
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import (
    Ability,
    Base,
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
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def seed_species_stubs(session, ids_names: dict[int, str]) -> None:
    for species_id, name in ids_names.items():
        session.add(Species(id=species_id, name=name, generation=1))


def test_extract_id_parses_pokeapi_urls() -> None:
    assert extract_id("https://pokeapi.co/api/v2/type/12/") == 12
    assert extract_id("https://pokeapi.co/api/v2/pokemon-species/1") == 1
    with pytest.raises(NormalizationError):
        extract_id("https://pokeapi.co/api/v2/type/grass/")


def test_species_normalization_creates_row_and_english_flavors(session_factory) -> None:
    with session_factory() as session:
        normalize_species(session, load("species_bulbasaur.json"))
        session.commit()

        species = session.get(Species, 1)
        assert species.name == "bulbasaur"
        assert species.generation == 1
        assert species.color == "green"
        assert species.habitat == "grassland"
        assert species.evolution_chain_id == 1
        flavors = session.scalars(select(FlavorText)).all()
        assert {(f.version, f.language) for f in flavors} == {("red", "en"), ("blue", "en")}
        assert "\n" not in flavors[0].text


def test_pokemon_normalization_populates_all_children(session_factory) -> None:
    with session_factory() as session:
        normalize_species(session, load("species_bulbasaur.json"))
        normalize_pokemon(session, load("pokemon_bulbasaur.json"))
        session.commit()

        pokemon = session.get(Pokemon, 1)
        assert pokemon.name == "bulbasaur"
        assert pokemon.species_id == 1
        assert pokemon.height == 7 and pokemon.weight == 69

        types = session.scalars(select(PokemonType).order_by(PokemonType.slot)).all()
        assert [(t.slot, t.type_id) for t in types] == [(1, 12), (2, 4)]

        abilities = session.scalars(select(PokemonAbility).order_by(PokemonAbility.slot)).all()
        assert [(a.ability_id, a.is_hidden) for a in abilities] == [(65, False), (34, True)]

        stats = {s.stat_name: s.base_value for s in session.scalars(select(PokemonStat))}
        assert stats["hp"] == 45 and stats["special-attack"] == 65

        moves = session.scalars(select(PokemonMove)).all()
        # tackle appears in two version groups but collapses to one (level-up, 1) row
        assert {(m.move_id, m.learn_method, m.level) for m in moves} == {
            (33, "level-up", 1),
            (75, "level-up", 20),
        }
        # stub rows for referenced entities
        assert session.get(Move, 33).name == "tackle"
        assert session.get(Ability, 34).name == "chlorophyll"

        sprites = {s.kind: s.source_url for s in session.scalars(select(Sprite))}
        assert set(sprites) == {"default", "shiny", "official-artwork"}
        assert sprites["default"].endswith("/pokemon/1.png")


def test_pokemon_without_species_fails_fast(session_factory) -> None:
    with session_factory() as session, pytest.raises(NormalizationError, match="Species 1"):
        normalize_pokemon(session, load("pokemon_bulbasaur.json"))


def test_normalization_is_idempotent(session_factory) -> None:
    with session_factory() as session:
        for _ in range(2):
            normalize_species(session, load("species_bulbasaur.json"))
            normalize_pokemon(session, load("pokemon_bulbasaur.json"))
            session.commit()

        counts = {
            table.name: session.execute(select(func.count()).select_from(table)).scalar_one()
            for table in Base.metadata.sorted_tables
        }
        assert counts["pokemon"] == 1
        assert counts["pokemon_types"] == 2
        assert counts["pokemon_abilities"] == 2
        assert counts["pokemon_stats"] == 6
        assert counts["pokemon_moves"] == 2
        assert counts["flavor_texts"] == 2
        assert counts["sprites"] == 3


def test_evolution_chain_creates_edges(session_factory) -> None:
    with session_factory() as session:
        seed_species_stubs(session, {1: "bulbasaur", 2: "ivysaur", 3: "venusaur"})
        for _ in range(2):  # idempotent
            normalize_evolution_chain(session, load("evolution_chain_1.json"))
            session.commit()

        edges = session.scalars(select(Evolution).order_by(Evolution.to_species_id)).all()
        assert [(e.from_species_id, e.to_species_id, e.min_level) for e in edges] == [
            (1, 2, 16),
            (2, 3, 32),
        ]
        assert all(e.trigger == "level-up" and e.chain_id == 1 for e in edges)
        assert edges[0].conditions["details"][0]["min_level"] == 16


def test_full_move_and_ability_enrich_stub_rows(session_factory) -> None:
    with session_factory() as session:
        normalize_species(session, load("species_bulbasaur.json"))
        normalize_pokemon(session, load("pokemon_bulbasaur.json"))  # creates stubs
        normalize_move(session, load("move_razor_leaf.json"))
        normalize_ability(session, load("ability_overgrow.json"))
        session.commit()

        move = session.get(Move, 75)
        assert move.power == 55 and move.accuracy == 95
        assert move.type_id == 12
        assert move.damage_class == "physical"
        assert "critical" in move.effect_text

        ability = session.get(Ability, 65)
        assert ability.effect_text.startswith("Strengthens grass moves")
