"""Golden case schema + loader.

Each case is its own YAML file (`cases/<suite>/<case_id>.yaml`) so adding one — by hand
or via the future `evals add-regression` command (5.7) — is a single-file diff.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class GoldenCase(BaseModel):
    case_id: str
    suite: str
    input: dict[str, Any]
    expected: dict[str, Any]
    origin: str


def load_cases(cases_dir: Path, suite: str | None = None) -> list[GoldenCase]:
    cases: dict[str, GoldenCase] = {}
    for path in sorted(cases_dir.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        case = GoldenCase(**data)
        if case.case_id in cases:
            raise ValueError(
                f"duplicate case_id {case.case_id!r}: {path} collides with an earlier file"
            )
        cases[case.case_id] = case
    selected = [c for c in cases.values() if suite is None or c.suite == suite]
    return sorted(selected, key=lambda c: c.case_id)
