from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, EvalResult, EvalRun, RawSnapshot


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


def test_eval_run_and_result_roundtrip(session_factory) -> None:
    with session_factory() as session:
        run = EvalRun(
            suite="text_retrieval",
            api_base_url="http://localhost:8001",
            case_count=30,
            summary={"recall_at_k": 1.0, "mrr": 1.0},
            started_at=datetime(2026, 8, 6, tzinfo=UTC),
        )
        session.add(run)
        session.commit()
        session.add(
            EvalResult(
                run_id=run.id,
                case_id="text_retrieval_001",
                retrieved_ids=[1, 1, 2, 1, 1],
                metrics={"recall_at_k": 1.0, "ndcg_at_k": 1.0},
            )
        )
        session.commit()

    with session_factory() as session:
        stored_run = session.scalars(select(EvalRun)).one()
        assert stored_run.summary["mrr"] == 1.0
        stored_result = session.scalars(select(EvalResult)).one()
        assert stored_result.run_id == stored_run.id
        assert stored_result.retrieved_ids == [1, 1, 2, 1, 1]
        assert stored_result.metrics["recall_at_k"] == 1.0


def test_duplicate_case_id_within_the_same_run_violates_unique_constraint(
    session_factory,
) -> None:
    with session_factory() as session:
        run = EvalRun(
            suite="text_retrieval",
            api_base_url="http://localhost:8001",
            case_count=1,
            started_at=datetime(2026, 8, 6, tzinfo=UTC),
        )
        session.add(run)
        session.commit()
        session.add(EvalResult(run_id=run.id, case_id="c1", metrics={}))
        session.commit()
        session.add(EvalResult(run_id=run.id, case_id="c1", metrics={}))
        with pytest.raises(IntegrityError):
            session.commit()
