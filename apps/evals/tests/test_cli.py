import respx
from typer.testing import CliRunner

from evals.cli import app
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, RagAnswer

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


def make_sqlite_url_with_answer(tmp_path, question: str) -> str:
    url = f"sqlite+pysqlite:///{tmp_path}/regress.db"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        session.add(RagAnswer(request_id="r1", question=question, status="answered", answer="x"))
        session.commit()
    return url


def test_add_regression_requires_an_assertion(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", make_sqlite_url_with_answer(tmp_path, "q"))

    result = runner.invoke(
        app, ["add-regression", "--answer-id", "1", "--cases-dir", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "Nothing to assert" in result.output


def test_add_regression_writes_a_loadable_case(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", make_sqlite_url_with_answer(tmp_path, "what type is bulbasaur?")
    )

    result = runner.invoke(
        app,
        [
            "add-regression",
            "--answer-id",
            "1",
            "--must-contain",
            "grass",
            "--must-contain",
            "poison",
            "--cases-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "wrote" in result.output

    from evals.cases import load_cases

    cases = load_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].input == {"question": "what type is bulbasaur?"}
    assert cases[0].expected["must_contain"] == ["grass", "poison"]
    assert cases[0].origin == "regression:1"


def test_add_regression_fails_fast_on_an_unknown_answer_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", make_sqlite_url_with_answer(tmp_path, "q"))

    result = runner.invoke(
        app,
        [
            "add-regression",
            "--answer-id",
            "999",
            "--must-contain",
            "x",
            "--cases-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "999" in result.output
