import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from evals.cases import load_cases
from evals.client import ApiClient
from evals.regression import AnswerNotFoundError, fetch_answer_question, write_regression_case
from evals.scoring import (
    score_case,
    score_comparison,
    score_rag_quality,
    summarize,
    summarize_comparison,
    summarize_rag_quality,
)
from evals.settings import EvalsSettings
from pokedex_common.logging import configure_logging
from pokedex_common.request_id import new_request_id, set_request_id

app = typer.Typer(name="evals", help="Golden-dataset evaluation runner (run-and-exit job).")

logger = logging.getLogger(__name__)


FAKE_API_URL = "fake://offline"


def bootstrap() -> EvalsSettings:
    settings = EvalsSettings.load()
    configure_logging(component="evals", level=settings.log_level)
    set_request_id(new_request_id())
    return settings


def make_client(api_url: str, fake_api: bool):
    """Real HTTP client, or the offline pipeline-integrity fake (Phase 6.3)."""
    if fake_api:
        from evals.fakes import FakeApiClient

        return FakeApiClient()
    return ApiClient(api_url)


@app.command("list-cases")
def list_cases(
    suite: Annotated[str | None, typer.Option(help="Only list cases in this suite")] = None,
    cases_dir: Annotated[
        Path | None, typer.Option(help="Override the configured cases directory")
    ] = None,
) -> None:
    """List golden cases without calling the API — a sanity check on the case files."""
    settings = bootstrap()
    directory = cases_dir or Path(settings.cases_dir)
    cases = load_cases(directory, suite=suite)
    for case in cases:
        summary = case.input.get("query") or case.input.get("question") or case.input
        typer.echo(f"{case.case_id} [{case.suite}] {summary}")
    typer.echo(f"total: {len(cases)}")


def _run_one_case(case, client: ApiClient, data_dir: Path, space: str | None = None):
    """Returns (score, echo_line) or raises for an unsupported suite."""
    if case.suite == "text_retrieval":
        result = client.search_text(**case.input, space=space)
        hit_ids = [r["pokemon_id"] for r in result["results"]]
        score = score_case(case, hit_ids)
        return score, (
            f"{case.case_id}: hits={hit_ids} recall@k={score.recall_at_k:.2f} "
            f"rr={score.reciprocal_rank:.2f} top1={score.top_1_hit:.0f} "
            f"ndcg@k={score.ndcg_at_k:.2f}"
        )
    if case.suite == "visual_retrieval":
        image_path = data_dir / case.input["image_path"]
        result = client.search_image(image_path, limit=case.input.get("limit", 10))
        hit_ids = [r["pokemon_id"] for r in result["results"]]
        score = score_case(case, hit_ids)
        return score, (
            f"{case.case_id}: hits={hit_ids} recall@k={score.recall_at_k:.2f} "
            f"rr={score.reciprocal_rank:.2f} top1={score.top_1_hit:.0f} "
            f"ndcg@k={score.ndcg_at_k:.2f}"
        )
    if case.suite == "rag_quality":
        response = client.chat(**case.input)
        score = score_rag_quality(case, response)
        return score, (
            f"{case.case_id}: status={score.status} contains={score.must_contain_ok:.0f} "
            f"avoids={score.must_not_contain_ok:.0f} pass={score.passed:.0f}"
        )
    return None, f"{case.case_id}: unsupported suite {case.suite!r}, skipped"


@app.command()
def run(
    suite: Annotated[str | None, typer.Option(help="Only run cases in this suite")] = None,
    api_url: Annotated[
        str | None, typer.Option(help="Override the configured API base URL")
    ] = None,
    cases_dir: Annotated[
        Path | None, typer.Option(help="Override the configured cases directory")
    ] = None,
    space: Annotated[
        str | None,
        typer.Option(
            help="Embedding space label for text_retrieval cases (per-space comparison "
            "runs, Phase 6.1); omit for the API's primary space"
        ),
    ] = None,
    fake_api: Annotated[
        bool,
        typer.Option(
            "--fake-api",
            help="Run against a deterministic offline fake instead of a real API "
            "(pipeline integrity check: no network, no cost, arbitrary scores)",
        ),
    ] = False,
) -> None:
    """Run golden cases against the live API, score them (per-suite metrics), and
    persist one eval_run per suite if DATABASE_URL is configured."""
    settings = bootstrap()
    directory = cases_dir or Path(settings.cases_dir)
    cases = load_cases(directory, suite=suite)
    if not cases:
        typer.echo(f"no cases found under {directory} (suite={suite!r})")
        raise typer.Exit(code=1)
    if space and any(case.suite != "text_retrieval" for case in cases):
        typer.echo(
            "--space only applies to text_retrieval cases (other suites have no space "
            "parameter) — combine it with --suite text_retrieval"
        )
        raise typer.Exit(code=1)

    resolved_api_url = FAKE_API_URL if fake_api else (api_url or settings.api_base_url)
    data_dir = Path(settings.data_dir)
    scores_by_suite: dict[str, list] = {}
    started_at = datetime.now(UTC)
    with make_client(resolved_api_url, fake_api) as client:
        for case in cases:
            score, line = _run_one_case(case, client, data_dir, space=space)
            typer.echo(line)
            if score is not None:
                logger.info("case scored", extra={"case_id": case.case_id, "suite": case.suite})
                scores_by_suite.setdefault(case.suite, []).append(score)
    finished_at = datetime.now(UTC)

    typer.echo(f"ran {len(cases)} case(s)")
    if not scores_by_suite:
        return

    if settings.database_url:
        from evals.persistence import save_run
        from pokedex_db.engine import create_db_engine, create_session_factory

        engine = create_db_engine(settings.database_url)
        session_factory = create_session_factory(engine)

    for suite_name, suite_scores in scores_by_suite.items():
        summarizer = summarize_rag_quality if suite_name == "rag_quality" else summarize
        summary = summarizer(suite_scores)
        typer.echo(
            f"[{suite_name}] suite averages: "
            + " ".join(f"{name}={value:.3f}" for name, value in summary.items())
        )
        if space:
            # Recorded alongside the metric means: a per-space run must stay
            # attributable to its space when compared later (never cross-space).
            summary = {**summary, "space": space}
        if not settings.database_url:
            continue
        run_id = save_run(
            session_factory,
            suite=suite_name,
            api_base_url=resolved_api_url,
            started_at=started_at,
            finished_at=finished_at,
            scores=suite_scores,
            summary=summary,
        )
        typer.echo(f"[{suite_name}] persisted as eval_runs.id={run_id}")

    if not settings.database_url:
        typer.echo("DATABASE_URL not configured — run not persisted")


@app.command()
def compare(
    suite: Annotated[str, typer.Option(help="Suite whose questions drive the comparison")] = (
        "rag_quality"
    ),
    providers: Annotated[
        list[str] | None,
        typer.Option(help="Provider to include (repeatable); omit for the API's default pair"),
    ] = None,
    api_url: Annotated[
        str | None, typer.Option(help="Override the configured API base URL")
    ] = None,
    cases_dir: Annotated[
        Path | None, typer.Option(help="Override the configured cases directory")
    ] = None,
    fake_api: Annotated[
        bool,
        typer.Option("--fake-api", help="Run against the offline fake (pipeline integrity)"),
    ] = False,
) -> None:
    """Run every case through POST /compare and score each provider separately.

    One eval_run per provider (summary tagged `comparison=1`), so a provider's numbers
    stay attributable and comparable against its own history — the API guarantees all
    providers saw the identical retrieved context.
    """
    settings = bootstrap()
    directory = cases_dir or Path(settings.cases_dir)
    cases = load_cases(directory, suite=suite)
    if not cases:
        typer.echo(f"no cases found under {directory} (suite={suite!r})")
        raise typer.Exit(code=1)
    unsupported = [c.case_id for c in cases if "question" not in c.input]
    if unsupported:
        typer.echo(f"/compare needs question-shaped cases; these have none: {unsupported}")
        raise typer.Exit(code=1)

    resolved_api_url = FAKE_API_URL if fake_api else (api_url or settings.api_base_url)
    scores_by_provider: dict[str, list] = {}
    started_at = datetime.now(UTC)
    with make_client(resolved_api_url, fake_api) as client:
        for case in cases:
            response = client.compare(case.input["question"], providers=providers or None)
            for candidate in response["candidates"]:
                score = score_comparison(case, candidate)
                scores_by_provider.setdefault(score.provider, []).append(score)
                grounded = "-" if score.judge_grounded is None else int(score.judge_grounded)
                typer.echo(
                    f"{case.case_id} [{score.provider}]: status={candidate.get('status')} "
                    f"pass={score.passed:.0f} grounded={grounded} {score.latency_ms}ms"
                )
    finished_at = datetime.now(UTC)
    typer.echo(f"ran {len(cases)} case(s) against {len(scores_by_provider)} provider(s)")

    if settings.database_url:
        from evals.persistence import save_run
        from pokedex_db.engine import create_db_engine, create_session_factory

        engine = create_db_engine(settings.database_url)
        session_factory = create_session_factory(engine)

    for provider, provider_scores in scores_by_provider.items():
        summary = {**summarize_comparison(provider_scores), "comparison": 1.0}
        typer.echo(
            f"[{provider}] "
            + " ".join(f"{k}={v:.3f}" for k, v in summary.items() if k != "comparison")
        )
        if not settings.database_url:
            continue
        run_id = save_run(
            session_factory,
            suite=suite,
            api_base_url=resolved_api_url,
            started_at=started_at,
            finished_at=finished_at,
            scores=provider_scores,
            summary={**summary, "provider": provider},
        )
        typer.echo(f"[{provider}] persisted as eval_runs.id={run_id}")

    if not settings.database_url:
        typer.echo("DATABASE_URL not configured — runs not persisted")


@app.command()
def report(
    run_id: Annotated[
        int | None, typer.Option(help="eval_runs.id to report on; omit for the latest run")
    ] = None,
    suite: Annotated[
        str | None, typer.Option(help="With no --run-id, report the latest run of this suite")
    ] = None,
    output: Annotated[
        Path | None, typer.Option(help="Write the markdown here instead of stdout")
    ] = None,
    git_sha: Annotated[str, typer.Option(help="Commit the run was made against")] = "unknown",
) -> None:
    """Render one eval run as a portfolio-ready markdown report (Phase 6.4).

    Quality metrics come from the run itself; latency percentiles, tokens and cost per
    answer are mined from the rag_answers rows written inside the run's time window.
    """
    from datetime import datetime as _datetime

    from evals.reporting import (
        ReportError,
        load_answers,
        load_run,
        parse_pricing,
        render_report,
        summarize_answers,
    )
    from pokedex_db.engine import create_db_engine, create_session_factory
    from pokedex_db.models import EvalResult

    settings = bootstrap()
    if not settings.database_url:
        typer.echo("DATABASE_URL is required to read eval runs")
        raise typer.Exit(code=1)
    try:
        prices = parse_pricing(settings.model_pricing_json)
    except ReportError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    session_factory = create_session_factory(create_db_engine(settings.database_url))
    with session_factory() as session:
        try:
            run = load_run(session, run_id, suite)
        except ReportError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        from sqlalchemy import select as _select

        results = list(
            session.scalars(
                _select(EvalResult).where(EvalResult.run_id == run.id).order_by(EvalResult.id)
            )
        )
        stats = summarize_answers(load_answers(session, run), prices)
        markdown = render_report(
            run,
            results,
            stats,
            git_sha=git_sha,
            generated_at=_datetime.now(UTC),
        )

    if output is None:
        typer.echo(markdown)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    typer.echo(f"wrote {output}")


@app.command("add-regression")
def add_regression(
    answer_id: Annotated[int, typer.Option(help="rag_answers.id to promote into a golden case")],
    status: Annotated[str, typer.Option(help="Expected status going forward")] = "answered",
    must_contain: Annotated[
        list[str] | None, typer.Option(help="Substring the answer must contain (repeatable)")
    ] = None,
    must_not_contain: Annotated[
        list[str] | None,
        typer.Option(help="Substring the answer must never contain (repeatable)"),
    ] = None,
    suite: Annotated[str, typer.Option(help="Suite to file the case under")] = "rag_quality",
    cases_dir: Annotated[
        Path | None, typer.Option(help="Override the configured cases directory")
    ] = None,
) -> None:
    """Promote a real /chat interaction into a permanent golden case — the fix for a
    real bug becomes a regression test, not just a patch.

    The QUESTION comes from the captured rag_answers row; the expected behavior
    (--status/--must-contain/--must-not-contain) is what YOU assert going forward —
    the captured answer is presumably the bad one being fixed, not the target.
    """
    settings = bootstrap()
    if not settings.database_url:
        typer.echo("DATABASE_URL is required to fetch the rag_answers row")
        raise typer.Exit(code=1)
    if not must_contain and not must_not_contain and status == "answered":
        typer.echo(
            "Nothing to assert: pass --must-contain/--must-not-contain, or "
            "--status insufficient_evidence, so the case actually checks something"
        )
        raise typer.Exit(code=1)

    from pokedex_db.engine import create_db_engine, create_session_factory

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        question = fetch_answer_question(session_factory, answer_id)
    except AnswerNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    directory = cases_dir or Path(settings.cases_dir)
    path = write_regression_case(
        directory,
        answer_id=answer_id,
        question=question,
        suite=suite,
        status=status,
        must_contain=must_contain,
        must_not_contain=must_not_contain,
    )
    typer.echo(f"wrote {path}")
