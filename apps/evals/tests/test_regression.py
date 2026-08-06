import pytest

from evals.cases import load_cases
from evals.regression import AnswerNotFoundError, fetch_answer_question, write_regression_case
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, RagAnswer


def make_session_factory_with_answer(question: str = "what type is bulbasaur?") -> tuple:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        answer = RagAnswer(
            request_id="req-1",
            question=question,
            status="answered",
            answer="Bulbasaur is a Water type [1].",  # the bad answer being fixed
        )
        session.add(answer)
        session.commit()
        answer_id = answer.id
    return session_factory, answer_id


def test_fetch_answer_question_returns_the_captured_question() -> None:
    session_factory, answer_id = make_session_factory_with_answer()

    assert fetch_answer_question(session_factory, answer_id) == "what type is bulbasaur?"


def test_fetch_answer_question_raises_when_the_id_does_not_exist() -> None:
    session_factory, _ = make_session_factory_with_answer()

    with pytest.raises(AnswerNotFoundError, match="999"):
        fetch_answer_question(session_factory, 999)


def test_write_regression_case_produces_a_file_load_cases_can_read_back(tmp_path) -> None:
    path = write_regression_case(
        tmp_path,
        answer_id=42,
        question="what type is bulbasaur?",
        must_contain=["grass", "poison"],
        must_not_contain=["water"],
    )

    assert path.exists()
    cases = load_cases(tmp_path)
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "regression_000042"
    assert case.suite == "rag_quality"
    assert case.input == {"question": "what type is bulbasaur?"}
    assert case.expected == {
        "status": "answered",
        "must_contain": ["grass", "poison"],
        "must_not_contain": ["water"],
    }
    assert case.origin == "regression:42"


def test_write_regression_case_omits_empty_must_lists(tmp_path) -> None:
    path = write_regression_case(
        tmp_path,
        answer_id=7,
        question="what is bulbasaur's favorite food?",
        status="insufficient_evidence",
    )

    case = load_cases(tmp_path)[0]
    assert case.expected == {"status": "insufficient_evidence"}
    assert path.parent.name == "rag_quality"


def test_write_regression_case_files_under_the_requested_suite(tmp_path) -> None:
    write_regression_case(
        tmp_path, answer_id=1, question="q", suite="custom_suite", must_contain=["x"]
    )

    assert (tmp_path / "custom_suite").is_dir()
    assert load_cases(tmp_path)[0].suite == "custom_suite"
