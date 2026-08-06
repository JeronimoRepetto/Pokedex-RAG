import logging
from pathlib import Path
from typing import Annotated

import typer

from evals.cases import load_cases
from evals.client import ApiClient
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
        typer.echo(f"{case.case_id} [{case.suite}] {case.input.get('query', case.input)}")
    typer.echo(f"total: {len(cases)}")


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
    """Run golden cases against the live API and print raw responses.

    No scoring yet (metrics land in Phase 5.2) — this establishes the plumbing:
    load cases, call the real API, surface what came back.
    """
    settings = bootstrap()
    directory = cases_dir or Path(settings.cases_dir)
    cases = load_cases(directory, suite=suite)
    if not cases:
        typer.echo(f"no cases found under {directory} (suite={suite!r})")
        raise typer.Exit(code=1)

    with ApiClient(api_url or settings.api_base_url) as client:
        for case in cases:
            if case.suite == "text_retrieval":
                result = client.search_text(**case.input)
                hit_ids = [r["pokemon_id"] for r in result["results"]]
                logger.info("case run", extra={"case_id": case.case_id, "hits": hit_ids})
                typer.echo(f"{case.case_id}: hits={hit_ids} expected={case.expected}")
            else:
                typer.echo(f"{case.case_id}: unsupported suite {case.suite!r}, skipped")
    typer.echo(f"ran {len(cases)} case(s)")
