"""normalize_type now keeps the damage relations it used to discard (Phase 8)."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from pipeline.normalize import normalize_type
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, Type, TypeEffectiveness

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def pairs(session) -> dict[tuple[str, str], float]:
    names = dict(session.execute(select(Type.id, Type.name)).all())
    return {
        (names[a], names[d]): m
        for a, d, m in session.execute(
            select(
                TypeEffectiveness.attacking_type_id,
                TypeEffectiveness.defending_type_id,
                TypeEffectiveness.multiplier,
            )
        ).all()
    }


def test_offensive_relations_are_stored(session_factory) -> None:
    with session_factory() as session:
        normalize_type(session, load("type_psychic.json"))
        session.commit()

        chart = pairs(session)

    assert chart[("psychic", "poison")] == 2.0
    assert chart[("psychic", "steel")] == 0.5
    assert chart[("psychic", "dark")] == 0.0


def test_defensive_relations_are_stored_in_the_right_direction(session_factory) -> None:
    """`double_damage_from: bug` on the psychic payload means BUG attacks PSYCHIC for 2x,
    not the other way round. Getting this backwards would invert half the chart."""
    with session_factory() as session:
        normalize_type(session, load("type_psychic.json"))
        session.commit()

        chart = pairs(session)

    assert chart[("bug", "psychic")] == 2.0
    assert chart[("ghost", "psychic")] == 2.0
    assert chart[("fighting", "psychic")] == 0.5
    assert ("psychic", "bug") not in chart


def test_a_type_with_no_snapshot_of_its_own_still_gets_a_row(session_factory) -> None:
    """Dark is referenced by other types but no Gen-1 Pokémon is Dark, so `type/17` is
    never fetched. Without stubbing it this is an FK violation on PostgreSQL — and
    silently accepted on SQLite, which is exactly how this bug class hides."""
    with session_factory() as session:
        normalize_type(session, load("type_psychic.json"))
        session.commit()

        dark = session.scalar(select(Type).where(Type.name == "dark"))
        chart = pairs(session)

    assert dark is not None
    assert chart[("dark", "psychic")] == 2.0  # would be missing if only *_to were read


def test_neutral_pairs_are_never_stored(session_factory) -> None:
    """The storage contract: absence means 1x. Storing neutrals would triple the table
    and invent rows PokéAPI never states."""
    with session_factory() as session:
        normalize_type(session, load("type_psychic.json"))
        session.commit()

        chart = pairs(session)

    assert all(multiplier != 1.0 for multiplier in chart.values())
    assert ("psychic", "normal") not in chart


def test_past_damage_relations_are_ignored(session_factory) -> None:
    """The fixture's generation-i block says Ghost does NO damage to Psychic. The modern
    chart says 2x. We follow the modern chart deliberately (the corpus already carries
    modern typings), so the past block must not leak in."""
    with session_factory() as session:
        normalize_type(session, load("type_psychic.json"))
        session.commit()

        chart = pairs(session)

    assert chart[("ghost", "psychic")] == 2.0


def test_renormalizing_converges(session_factory) -> None:
    """Snapshots are immutable and ingest re-runs; a second pass must not duplicate rows
    or change values."""
    with session_factory() as session:
        normalize_type(session, load("type_psychic.json"))
        session.commit()
        first = pairs(session)

        normalize_type(session, load("type_psychic.json"))
        session.commit()
        second = pairs(session)

    assert first == second


def test_a_payload_without_relations_is_tolerated(session_factory) -> None:
    with session_factory() as session:
        normalize_type(session, {"id": 1, "name": "normal"})
        session.commit()

        assert session.scalar(select(Type).where(Type.name == "normal")) is not None
        assert pairs(session) == {}
