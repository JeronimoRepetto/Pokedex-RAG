"""Promote a real `rag_answers` row into a permanent golden case (Phase 5.7) — the fix
for a real bug becomes a regression test, not just a patch, closing the loop devlog
0019 opened when `rag_answers` was built as "the mining ground for regression cases".

The captured row supplies the QUESTION only — the correct expected behavior (status,
required/forbidden facts) is supplied by whoever is promoting the case, since the
captured answer is presumably the bad one being fixed, not the target to assert.
"""

import re
from pathlib import Path

import yaml
from sqlalchemy.orm import Session, sessionmaker

from evals.cases import GoldenCase
from pokedex_db.models import RagAnswer


class AnswerNotFoundError(LookupError):
    pass


def fetch_answer_question(session_factory: sessionmaker[Session], answer_id: int) -> str:
    with session_factory() as session:
        row = session.get(RagAnswer, answer_id)
    if row is None:
        raise AnswerNotFoundError(f"no rag_answers row with id={answer_id}")
    return row.question


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len] or "case"


def _to_yaml(case: GoldenCase) -> str:
    return yaml.safe_dump(
        {
            "case_id": case.case_id,
            "suite": case.suite,
            "input": case.input,
            "expected": case.expected,
            "origin": case.origin,
        },
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def write_regression_case(
    cases_dir: Path,
    *,
    answer_id: int,
    question: str,
    suite: str = "rag_quality",
    status: str = "answered",
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
) -> Path:
    expected: dict = {"status": status}
    if must_contain:
        expected["must_contain"] = must_contain
    if must_not_contain:
        expected["must_not_contain"] = must_not_contain

    case = GoldenCase(
        case_id=f"regression_{answer_id:06d}",
        suite=suite,
        input={"question": question},
        expected=expected,
        origin=f"regression:{answer_id}",
    )
    target_dir = cases_dir / suite
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{case.case_id}_{_slugify(question)}.yaml"
    path.write_text(_to_yaml(case), encoding="utf-8")
    return path
