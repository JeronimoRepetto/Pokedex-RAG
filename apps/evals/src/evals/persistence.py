"""Persist an eval run + its per-case results (eval_runs/eval_results, migration 0005)."""

from dataclasses import asdict
from datetime import datetime

from evals.scoring import CaseScore
from pokedex_db.models import EvalResult, EvalRun


def save_run(
    session_factory,
    *,
    suite: str,
    api_base_url: str,
    started_at: datetime,
    finished_at: datetime,
    scores: list[CaseScore],
    summary: dict[str, float],
) -> int:
    with session_factory() as session:
        run = EvalRun(
            suite=suite,
            api_base_url=api_base_url,
            case_count=len(scores),
            summary=summary,
            started_at=started_at,
            finished_at=finished_at,
        )
        session.add(run)
        session.flush()  # assigns run.id without committing yet
        for score in scores:
            fields = asdict(score)
            session.add(
                EvalResult(
                    run_id=run.id,
                    case_id=fields.pop("case_id"),
                    retrieved_ids=fields.pop("retrieved_ids"),
                    metrics=fields,
                )
            )
        session.commit()
        return run.id
