"""Report generator (Phase 6.4): percentiles, pricing, and markdown rendering."""

from datetime import UTC, datetime, timedelta

import pytest

from evals.reporting import (
    AnswerStats,
    ModelPrice,
    ReportError,
    load_answers,
    load_run,
    parse_pricing,
    percentile,
    render_report,
    summarize_answers,
)
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, EvalResult, EvalRun, RagAnswer

START = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


# --- percentile -----------------------------------------------------------------


def test_median_of_an_odd_sample() -> None:
    assert percentile([3.0, 1.0, 2.0], 0.5) == 2.0


def test_median_interpolates_on_an_even_sample() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5


def test_a_single_value_is_every_percentile() -> None:
    """A one-case run is a legitimate report; statistics.quantiles would raise here."""
    assert percentile([42.0], 0.5) == 42.0
    assert percentile([42.0], 0.95) == 42.0


def test_extremes_are_the_min_and_max() -> None:
    values = [5.0, 1.0, 9.0]

    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 1.0) == 9.0


def test_p95_of_twenty_values_lands_near_the_top() -> None:
    assert percentile([float(v) for v in range(1, 21)], 0.95) == pytest.approx(19.05)


def test_the_input_list_is_not_mutated() -> None:
    values = [3.0, 1.0, 2.0]

    percentile(values, 0.5)

    assert values == [3.0, 1.0, 2.0]


def test_empty_and_out_of_range_are_errors() -> None:
    with pytest.raises(ValueError, match="empty"):
        percentile([], 0.5)
    with pytest.raises(ValueError, match=r"0\.\.1"):
        percentile([1.0], 1.5)


# --- pricing --------------------------------------------------------------------


def test_pricing_parses_a_model_table() -> None:
    prices = parse_pricing('{"m": {"input_per_1m": 0.3, "output_per_1m": 2.5}}')

    assert prices["m"] == ModelPrice(input_per_1m=0.3, output_per_1m=2.5)


def test_cost_is_per_million_tokens() -> None:
    price = ModelPrice(input_per_1m=1.0, output_per_1m=10.0)

    assert price.cost(1_000_000, 0) == pytest.approx(1.0)
    assert price.cost(0, 100_000) == pytest.approx(1.0)


def test_empty_pricing_is_an_empty_table_not_an_error() -> None:
    assert parse_pricing("") == {}
    assert parse_pricing("   ") == {}


def test_malformed_pricing_fails_fast() -> None:
    with pytest.raises(ReportError, match="valid JSON"):
        parse_pricing("{not json")
    with pytest.raises(ReportError, match="object keyed by model"):
        parse_pricing("[1, 2]")
    with pytest.raises(ReportError, match="numeric"):
        parse_pricing('{"m": {"input_per_1m": "free"}}')


# --- answer stats ---------------------------------------------------------------


def answer(**overrides) -> RagAnswer:
    base = {
        "request_id": "r",
        "question": "q",
        "status": "answered",
        "answer": "a",
        "provider": "p",
        "model": "m",
        "prompt_tokens": 1000,
        "output_tokens": 100,
        "latency_ms": 1000,
    }
    return RagAnswer(**{**base, **overrides})


def test_stats_aggregate_latency_and_tokens() -> None:
    prices = {"m": ModelPrice(input_per_1m=1.0, output_per_1m=10.0)}

    stats = summarize_answers([answer(), answer(latency_ms=3000)], prices)

    assert stats.answers == 2
    assert stats.latency_p50_ms == 2000
    assert stats.prompt_tokens == 2000
    assert stats.output_tokens == 200
    assert stats.cost_usd == pytest.approx(0.004)
    assert stats.cost_per_answer_usd == pytest.approx(0.002)


def test_unpriced_models_are_reported_not_guessed() -> None:
    stats = summarize_answers([answer(model="mystery-model")], {})

    assert stats.cost_usd is None
    assert stats.cost_per_answer_usd is None
    assert stats.unpriced_models == ("mystery-model",)


def test_partial_pricing_costs_what_it_can_and_names_the_gap() -> None:
    prices = {"m": ModelPrice(input_per_1m=1.0, output_per_1m=10.0)}

    stats = summarize_answers([answer(), answer(model="other")], prices)

    assert stats.cost_usd == pytest.approx(0.002)  # only the priced row
    assert stats.unpriced_models == ("other",)


def test_no_answers_yields_empty_stats() -> None:
    stats = summarize_answers([], {})

    assert stats == AnswerStats()
    assert stats.cost_per_answer_usd is None


def test_missing_latencies_are_skipped_not_zeroed() -> None:
    stats = summarize_answers([answer(latency_ms=None), answer(latency_ms=500)], {})

    assert stats.latency_p50_ms == 500


# --- run loading + rendering ----------------------------------------------------


@pytest.fixture
def session_factory(tmp_path):
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path}/report.db")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def make_run(session, *, suite="text_retrieval", summary=None, minutes=5) -> EvalRun:
    run = EvalRun(
        suite=suite,
        api_base_url="http://localhost:8000",
        case_count=2,
        summary=summary if summary is not None else {"recall_at_k": 1.0},
        started_at=START,
        finished_at=START + timedelta(minutes=minutes),
    )
    session.add(run)
    session.flush()
    return run


def test_load_run_by_id(session_factory) -> None:
    with session_factory() as session:
        run = make_run(session)
        session.commit()
        assert load_run(session, run.id, None).id == run.id


def test_load_run_defaults_to_the_latest(session_factory) -> None:
    with session_factory() as session:
        make_run(session, suite="text_retrieval")
        newest = make_run(session, suite="rag_quality")
        session.commit()

        assert load_run(session, None, None).id == newest.id


def test_load_run_can_filter_by_suite(session_factory) -> None:
    with session_factory() as session:
        wanted = make_run(session, suite="text_retrieval")
        make_run(session, suite="rag_quality")
        session.commit()

        assert load_run(session, None, "text_retrieval").id == wanted.id


def test_load_run_fails_fast_on_a_missing_id(session_factory) -> None:
    with session_factory() as session:
        with pytest.raises(ReportError, match="id=999"):
            load_run(session, 999, None)
        with pytest.raises(ReportError, match="no eval runs"):
            load_run(session, None, "nonexistent")


def test_answers_are_joined_by_the_run_time_window(session_factory) -> None:
    """rag_answers has no FK to eval_runs, so the window is the only honest join —
    answers from before or after the run must not be counted."""
    with session_factory() as session:
        run = make_run(session)
        session.add(answer(created_at=START + timedelta(minutes=1), question="inside"))
        session.add(answer(created_at=START - timedelta(minutes=1), question="before"))
        session.add(answer(created_at=START + timedelta(minutes=30), question="after"))
        session.commit()

        rows = load_answers(session, run)

    assert [r.question for r in rows] == ["inside"]


def test_report_renders_quality_and_operational_sections(session_factory) -> None:
    with session_factory() as session:
        run = make_run(session, summary={"recall_at_k": 1.0, "mrr": 0.983, "space": "gemma-v1"})
        session.commit()
        stats = summarize_answers([answer(), answer(latency_ms=2000)], {"m": ModelPrice(1.0, 10.0)})
        markdown = render_report(run, [], stats, git_sha="abc1234")

    assert "# Eval run" in markdown
    assert "| Git SHA | abc1234 |" in markdown
    assert "| Embedding space | gemma-v1 |" in markdown
    assert "| recall_at_k | 1.000 |" in markdown
    assert "| Latency p95 |" in markdown
    assert "Cost per answer" in markdown
    assert "evals report --run-id" in markdown


def test_report_names_unpriced_models_instead_of_showing_zero(session_factory) -> None:
    with session_factory() as session:
        run = make_run(session)
        session.commit()
        markdown = render_report(run, [], summarize_answers([answer(model="mystery")], {}))

    assert "no price configured" in markdown
    assert "mystery" in markdown
    assert "| Total cost | n/a USD |" in markdown


def test_report_explains_an_empty_operational_section(session_factory) -> None:
    with session_factory() as session:
        run = make_run(session)
        session.commit()
        markdown = render_report(run, [], AnswerStats())

    assert "retrieval-only suite" in markdown


def test_report_lists_failed_cases(session_factory) -> None:
    with session_factory() as session:
        run = make_run(session, suite="rag_quality", summary={"pass_rate": 0.5})
        results = [
            EvalResult(run_id=run.id, case_id="ok", retrieved_ids=[], metrics={"passed": 1.0}),
            EvalResult(
                run_id=run.id,
                case_id="bad",
                retrieved_ids=[],
                metrics={"passed": 0.0, "status_match": 0.0},
            ),
        ]
        session.add_all(results)
        session.commit()
        markdown = render_report(run, results, AnswerStats())

    assert "## Failed cases" in markdown
    assert "| bad |" in markdown
    assert "| ok |" not in markdown
