import respx
from typer.testing import CliRunner

from evals.cli import app

runner = CliRunner()
BASE = "http://api.test"


def write_case(directory, case_id: str) -> None:
    (directory / f"{case_id}.yaml").write_text(
        f"""case_id: {case_id}
suite: text_retrieval
input:
  query: "what type is bulbasaur"
  mode: hybrid
  limit: 5
expected:
  relevant_pokemon_ids: [1]
origin: handwritten
""",
        encoding="utf-8",
    )


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "list-cases" in result.output


def test_list_cases_prints_every_case(tmp_path) -> None:
    write_case(tmp_path, "text_retrieval_001")
    write_case(tmp_path, "text_retrieval_002")

    result = runner.invoke(app, ["list-cases", "--cases-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "text_retrieval_001" in result.output
    assert "text_retrieval_002" in result.output
    assert "total: 2" in result.output


def test_run_with_no_matching_cases_exits_nonzero(tmp_path) -> None:
    result = runner.invoke(app, ["run", "--cases-dir", str(tmp_path), "--suite", "rag_quality"])

    assert result.exit_code == 1


@respx.mock
def test_run_calls_the_api_and_reports_hits(tmp_path) -> None:
    write_case(tmp_path, "text_retrieval_001")
    respx.post(f"{BASE}/search/text").respond(
        json={"mode": "hybrid", "results": [{"pokemon_id": 1, "score": 0.9}]}
    )

    result = runner.invoke(app, ["run", "--cases-dir", str(tmp_path), "--api-url", BASE])

    assert result.exit_code == 0
    assert "text_retrieval_001" in result.output
    assert "hits=[1]" in result.output
    assert "ran 1 case(s)" in result.output
