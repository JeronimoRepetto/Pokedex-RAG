from datetime import UTC, datetime

from sqlalchemy import select

from evals.persistence import save_run
from evals.scoring import CaseScore, RagQualityScore
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, EvalResult, EvalRun


def make_session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def test_save_run_persists_the_run_and_every_case_result() -> None:
    session_factory = make_session_factory()
    scores = [
        CaseScore("c1", [1, 1], 1.0, 1.0, 1.0, 1.0),
        CaseScore("c2", [9], 0.0, 0.0, 0.0, 0.0),
    ]

    run_id = save_run(
        session_factory,
        suite="text_retrieval",
        api_base_url="http://localhost:8001",
        started_at=datetime(2026, 8, 6, tzinfo=UTC),
        finished_at=datetime(2026, 8, 6, 0, 1, tzinfo=UTC),
        scores=scores,
        summary={"recall_at_k": 0.5},
    )

    with session_factory() as session:
        run = session.get(EvalRun, run_id)
        assert run.suite == "text_retrieval"
        assert run.case_count == 2
        assert run.summary["recall_at_k"] == 0.5

        results = session.scalars(
            select(EvalResult).where(EvalResult.run_id == run_id).order_by(EvalResult.case_id)
        ).all()
        assert [r.case_id for r in results] == ["c1", "c2"]
        assert results[0].retrieved_ids == [1, 1]
        assert results[0].metrics["recall_at_k"] == 1.0
        assert results[1].metrics["recall_at_k"] == 0.0


def test_save_run_handles_rag_quality_scores_too() -> None:
    session_factory = make_session_factory()
    scores = [RagQualityScore("r1", "answered", ["1", "2"], 1.0, 1.0, 1.0, 1.0)]

    run_id = save_run(
        session_factory,
        suite="rag_quality",
        api_base_url="http://localhost:8001",
        started_at=datetime(2026, 8, 6, tzinfo=UTC),
        finished_at=datetime(2026, 8, 6, 0, 1, tzinfo=UTC),
        scores=scores,
        summary={"pass_rate": 1.0},
    )

    with session_factory() as session:
        result = session.scalars(select(EvalResult).where(EvalResult.run_id == run_id)).one()
        assert result.case_id == "r1"
        assert result.retrieved_ids == ["1", "2"]  # citation_document_ids, stored generically
        assert result.metrics["status"] == "answered"
        assert result.metrics["passed"] == 1.0
