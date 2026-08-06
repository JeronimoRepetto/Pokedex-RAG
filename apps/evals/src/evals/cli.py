import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from evals.cases import load_cases
from evals.client import ApiClient
from evals.scoring import score_case, score_rag_quality, summarize, summarize_rag_quality
from evals.settings import EvalsSettings
from pokedex_common.logging import configure_logging
from pokedex_common.request_id import new_request_id, set_request_id

app = typer.Typer(name="evals", help="Golden-dataset evaluation runner (run-and-exit job).")

logger = logging.getLogger(__name__)


def bootstrap() -> EvalsSettings:
    settings = EvalsSettings.load()
    configure_logging(component="evals", level=settings.log_level)
    set_request_id(new_request_id())
    return settings


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


def _run_one_case(case, client: ApiClient, data_dir: Path):
    """Returns (score, echo_line) or raises for an unsupported suite."""
    if case.suite == "text_retrieval":
        result = client.search_text(**case.input)
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
) -> None:
    """Run golden cases against the live API, score them (per-suite metrics), and
    persist one eval_run per suite if DATABASE_URL is configured."""
    settings = bootstrap()
    directory = cases_dir or Path(settings.cases_dir)
    cases = load_cases(directory, suite=suite)
    if not cases:
        typer.echo(f"no cases found under {directory} (suite={suite!r})")
        raise typer.Exit(code=1)

    resolved_api_url = api_url or settings.api_base_url
    data_dir = Path(settings.data_dir)
    scores_by_suite: dict[str, list] = {}
    started_at = datetime.now(UTC)
    with ApiClient(resolved_api_url) as client:
        for case in cases:
            score, line = _run_one_case(case, client, data_dir)
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
