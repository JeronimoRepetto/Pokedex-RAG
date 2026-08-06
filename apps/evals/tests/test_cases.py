from pathlib import Path

import pytest

from evals.cases import load_cases

REPO_CASES_DIR = Path(__file__).parent.parent / "cases"


def write_case(directory: Path, filename: str, **fields) -> None:
    defaults = {
        "case_id": "c1",
        "suite": "text_retrieval",
        "input": {"query": "what type is bulbasaur", "mode": "hybrid", "limit": 5},
        "expected": {"relevant_pokemon_ids": [1]},
        "origin": "handwritten",
    }
    defaults.update(fields)
    lines = [f"case_id: {defaults['case_id']}", f"suite: {defaults['suite']}"]
    lines.append("input:")
    for k, v in defaults["input"].items():
        lines.append(f"  {k}: {v!r}" if isinstance(v, str) else f"  {k}: {v}")
    lines.append("expected:")
    for k, v in defaults["expected"].items():
        lines.append(f"  {k}: {v}")
    lines.append(f"origin: {defaults['origin']}")
    (directory / filename).write_text("\n".join(lines), encoding="utf-8")


def test_loads_every_committed_golden_case_without_error() -> None:
    cases = load_cases(REPO_CASES_DIR)

    assert len(cases) >= 45  # 30 text_retrieval + 15 visual_retrieval
    assert {c.suite for c in cases} == {"text_retrieval", "visual_retrieval"}
    assert len({c.case_id for c in cases}) == len(cases)


def test_filters_by_suite(tmp_path: Path) -> None:
    write_case(tmp_path, "a.yaml", case_id="a1", suite="text_retrieval")
    write_case(tmp_path, "b.yaml", case_id="b1", suite="rag_quality")

    assert [c.case_id for c in load_cases(tmp_path, suite="rag_quality")] == ["b1"]
    assert [c.case_id for c in load_cases(tmp_path)] == ["a1", "b1"]


def test_duplicate_case_id_fails_fast(tmp_path: Path) -> None:
    write_case(tmp_path, "a.yaml", case_id="dup")
    write_case(tmp_path, "b.yaml", case_id="dup")

    with pytest.raises(ValueError, match="dup"):
        load_cases(tmp_path)


def test_cases_are_returned_sorted_by_case_id(tmp_path: Path) -> None:
    write_case(tmp_path, "a.yaml", case_id="c_002")
    write_case(tmp_path, "b.yaml", case_id="c_001")

    assert [c.case_id for c in load_cases(tmp_path)] == ["c_001", "c_002"]
