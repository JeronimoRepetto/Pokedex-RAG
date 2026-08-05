import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, RawSnapshot


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def make_snapshot(**overrides) -> RawSnapshot:
    defaults = {
        "resource_type": "pokemon",
        "resource_id": "25",
        "source_url": "https://pokeapi.co/api/v2/pokemon/25/",
        "payload": {"name": "pikachu", "types": [{"type": {"name": "electric"}}]},
        "sha256": "a" * 64,
    }
    defaults.update(overrides)
    return RawSnapshot(**defaults)


def test_snapshot_roundtrip_preserves_payload(session_factory) -> None:
    with session_factory() as session:
        session.add(make_snapshot())
        session.commit()

    with session_factory() as session:
        stored = session.scalars(select(RawSnapshot)).one()
        assert stored.resource_type == "pokemon"
        assert stored.resource_id == "25"
        assert stored.payload["name"] == "pikachu"
        assert stored.payload["types"][0]["type"]["name"] == "electric"
        assert stored.fetched_at is not None


def test_same_resource_twice_violates_unique_constraint(session_factory) -> None:
    with session_factory() as session:
        session.add(make_snapshot())
        session.commit()
        session.add(make_snapshot(sha256="b" * 64))
        with pytest.raises(IntegrityError):
            session.commit()


def test_different_resource_types_may_share_resource_id(session_factory) -> None:
    with session_factory() as session:
        session.add(make_snapshot())
        session.add(make_snapshot(resource_type="pokemon-species"))
        session.commit()
        assert len(session.scalars(select(RawSnapshot)).all()) == 2
