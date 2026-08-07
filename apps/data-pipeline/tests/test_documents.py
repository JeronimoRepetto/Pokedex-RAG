import json
from pathlib import Path

import pytest
from sqlalchemy import select

from pipeline.documents import DocumentBuilder
from pipeline.normalize import (
    normalize_ability,
    normalize_evolution_chain,
    normalize_move,
    normalize_pokemon,
    normalize_species,
)
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, Document, PokemonStat, Species

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        normalize_species(session, load("species_bulbasaur.json"))
        session.add(Species(id=2, name="ivysaur", generation=1, evolution_chain_id=1))
        session.add(Species(id=3, name="venusaur", generation=1, evolution_chain_id=1))
        normalize_pokemon(session, load("pokemon_bulbasaur.json"))
        normalize_evolution_chain(session, load("evolution_chain_1.json"))
        normalize_move(session, load("move_razor_leaf.json"))
        normalize_ability(session, load("ability_overgrow.json"))
        session.commit()
        yield session


def drafts_by_type(builder: DocumentBuilder) -> dict[str, object]:
    return {d.doc_type: d for d in builder.build_for_pokemon(1)}


def seed_type_chart(session) -> None:
    """Minimal chart so the matchup document has something to say. Bulbasaur is
    grass/poison in the fixture."""
    from pokedex_db.models import Type, TypeEffectiveness

    names = {1: "normal", 4: "poison", 3: "flying", 12: "grass", 11: "water", 10: "fire"}
    for type_id, name in names.items():
        session.merge(Type(id=type_id, name=name))
    session.flush()
    for attacking, defending, multiplier in [
        (3, 12, 2.0),  # flying -> grass
        (10, 12, 2.0),  # fire -> grass
        (11, 12, 0.5),  # water -> grass
        (12, 11, 2.0),  # grass -> water
        (12, 12, 0.5),  # grass -> grass
        (4, 12, 2.0),  # poison -> grass
        (4, 4, 0.5),  # poison -> poison
        # Deliberately NO flying->poison row: flying is neutral against poison in the
        # real chart, which is exactly why Bulbasaur ends up 2x weak to flying rather
        # than having it cancel out.
    ]:
        session.merge(
            TypeEffectiveness(
                attacking_type_id=attacking, defending_type_id=defending, multiplier=multiplier
            )
        )
    session.commit()


def test_builds_every_document_type(session) -> None:
    """Without a type chart the matchup document is correctly absent — a database that
    predates the Phase-8 migration must not produce an empty document."""
    drafts = drafts_by_type(DocumentBuilder(session))
    assert set(drafts) == {"card", "flavor", "moves", "evolution"}

    seed_type_chart(session)

    assert set(drafts_by_type(DocumentBuilder(session))) == {
        "card",
        "flavor",
        "moves",
        "evolution",
        "matchup",
    }


def test_matchup_document_states_both_sides_and_the_chart_generation(session) -> None:
    seed_type_chart(session)

    matchup = drafts_by_type(DocumentBuilder(session))["matchup"]

    assert matchup.title == "Bulbasaur (#1) — type matchups"
    # Defensive: fire and flying each hit grass 2x and are neutral on poison, so they
    # land at 2x — neither reaches 4x. Poison is 2x on grass but 0.5x on poison, so it
    # cancels to neutral and must NOT appear.
    assert "super effective (2x) against Bulbasaur: fire, flying" in matchup.content
    assert "Attacks Bulbasaur resists (0.5x): grass, water" in matchup.content
    # Offensive: its own grass attacks beat water.
    assert "grass attacks are super effective against: water" in matchup.content
    # The caveat has to live IN the document, or a model quoting it drops the caveat.
    assert "Generation VI onward" in matchup.content


def test_matchup_document_hash_is_stable_across_builds(session) -> None:
    """The embed job skips unchanged content by hash; an unstable document would pay to
    re-embed 151 documents on every build."""
    seed_type_chart(session)

    first = drafts_by_type(DocumentBuilder(session))["matchup"]
    second = drafts_by_type(DocumentBuilder(session))["matchup"]

    assert first.content_hash == second.content_hash


def test_card_contains_verifiable_facts(session) -> None:
    card = drafts_by_type(DocumentBuilder(session))["card"]

    assert card.title == "Bulbasaur (#1) — Pokédex card"
    assert "grass/poison type Pokémon from generation 1" in card.content
    assert "Height: 0.7 m. Weight: 6.9 kg." in card.content
    assert "Chlorophyll (hidden ability)" in card.content
    assert "Strengthens grass moves" in card.content  # enriched ability effect
    assert "HP 45, Attack 49, Defense 49, Special Attack 65" in card.content
    assert "Bulbasaur evolves into Ivysaur at level 16." in card.content
    # card mentions only edges touching this species, not the whole chain
    assert "Venusaur" not in card.content
    assert "https://pokeapi.co/api/v2/pokemon-species/1/" in card.source_refs["pokeapi"]


def test_flavor_document_dedupes_across_versions(session) -> None:
    flavor = drafts_by_type(DocumentBuilder(session))["flavor"]

    assert flavor.content.count("A strange seed was planted") == 1
    assert "versions: red, blue" in flavor.content


def test_moves_document_renders_levels_and_details(session) -> None:
    moves = drafts_by_type(DocumentBuilder(session))["moves"]

    assert "Tackle from the start" in moves.content
    assert "Razor Leaf (grass, power 55, accuracy 95) at level 20" in moves.content


def test_evolution_document_covers_full_chain(session) -> None:
    evolution = drafts_by_type(DocumentBuilder(session))["evolution"]

    assert "Bulbasaur evolves into Ivysaur at level 16." in evolution.content
    assert "Ivysaur evolves into Venusaur at level 32." in evolution.content


def test_builds_are_deterministic(session) -> None:
    builder = DocumentBuilder(session)
    first = {d.doc_type: d.content_hash for d in builder.build_for_pokemon(1)}
    second = {d.doc_type: d.content_hash for d in builder.build_for_pokemon(1)}
    assert first == second


def test_build_docs_cli_runs_end_to_end(tmp_path, monkeypatch) -> None:
    """Regression: logging `extra` with the reserved key 'created' crashed the command."""
    from typer.testing import CliRunner

    from pipeline.cli import app

    url = f"sqlite+pysqlite:///{tmp_path}/docs.db"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as seeding_session:
        normalize_species(seeding_session, load("species_bulbasaur.json"))
        normalize_pokemon(seeding_session, load("pokemon_bulbasaur.json"))
        seeding_session.commit()
    monkeypatch.setenv("DATABASE_URL", url)

    result = CliRunner().invoke(app, ["build-docs"])

    assert result.exit_code == 0, result.output
    # card + flavor + moves; no evolution doc because no chain was seeded here
    assert "created=3" in result.output


def test_upsert_converges_and_detects_changes(session) -> None:
    builder = DocumentBuilder(session)

    created, updated, unchanged = builder.upsert(builder.build_for_pokemon(1))
    session.commit()
    assert (created, updated, unchanged) == (4, 0, 0)

    created, updated, unchanged = builder.upsert(builder.build_for_pokemon(1))
    assert (created, updated, unchanged) == (0, 0, 4)

    # a real data change must flow into the document and its hash
    stat = session.get(PokemonStat, (1, "hp"))
    stat.base_value = 999
    session.flush()
    created, updated, unchanged = builder.upsert(builder.build_for_pokemon(1))
    assert updated == 1
    card = session.scalar(select(Document).where(Document.doc_type == "card"))
    assert "HP 999" in card.content
