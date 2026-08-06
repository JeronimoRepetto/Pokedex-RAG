"""Persist an eval run + its per-case results (eval_runs/eval_results, migration 0005).

Score-shape-agnostic: works with `CaseScore` (retrieval, `retrieved_ids`) and
`RagQualityScore` (`citation_document_ids`) alike, by duck-typing on whichever id
field a given score dataclass actually has.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from pokedex_db.models import EvalResult, EvalRun

_ID_FIELDS = ("retrieved_ids", "citation_document_ids")


def save_run(
    session_factory,
    *,
    suite: str,
    api_base_url: str,
    started_at: datetime,
    finished_at: datetime,
    scores: list[Any],
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
            case_id = fields.pop("case_id")
            ids = next((fields.pop(f) for f in _ID_FIELDS if f in fields), [])
            session.add(
                EvalResult(run_id=run.id, case_id=case_id, retrieved_ids=ids, metrics=fields)
            )
        session.commit()
        return run.id
