import pytest

from api.rag.context import BuiltContext, ContextDocument
from api.rag.judge import FakeJudge, JudgeParsingError, JudgeVerdict, LLMJudge
from pokedex_llm import FakeLLM

CONTEXT = BuiltContext(
    text="[1] Squirtle card\nSquirtle is a water type Pokémon.",
    citation_map={
        1: ContextDocument(
            document_id=1,
            title="Squirtle card",
            content="Squirtle is a water type Pokémon.",
            pokemon_id=7,
            pokemon_name="squirtle",
            doc_type="card",
        )
    },
)


def test_llm_judge_parses_a_valid_verdict() -> None:
    llm = FakeLLM(script=['{"grounded": true, "hallucination": false, "reasoning": "matches [1]"}'])
    judge = LLMJudge(llm)

    verdict = judge.judge("what type is squirtle?", "Squirtle is a water type [1].", CONTEXT)

    assert verdict == JudgeVerdict(
        grounded=True, hallucination_detected=False, reasoning="matches [1]"
    )
    request = llm.requests[0]
    assert request.response_mime_type == "application/json"


def test_llm_judge_defaults_missing_optional_fields() -> None:
    llm = FakeLLM(script=['{"grounded": false}'])
    judge = LLMJudge(llm)

    verdict = judge.judge("q", "a", CONTEXT)

    assert verdict.grounded is False
    assert verdict.hallucination_detected is False
    assert verdict.reasoning == ""


def test_llm_judge_raises_on_non_json_response() -> None:
    llm = FakeLLM(script=["sorry, I cannot comply"])
    judge = LLMJudge(llm)

    with pytest.raises(JudgeParsingError, match="unparseable"):
        judge.judge("q", "a", CONTEXT)


def test_llm_judge_raises_when_grounded_key_is_missing() -> None:
    llm = FakeLLM(script=['{"reasoning": "no grounded key here"}'])
    judge = LLMJudge(llm)

    with pytest.raises(JudgeParsingError):
        judge.judge("q", "a", CONTEXT)


def test_fake_judge_returns_scripted_verdicts_in_order() -> None:
    first = JudgeVerdict(grounded=False, hallucination_detected=True, reasoning="bad")
    second = JudgeVerdict(grounded=True, hallucination_detected=False, reasoning="ok now")
    judge = FakeJudge(script=[first, second])

    assert judge.judge("q", "a1", CONTEXT) == first
    assert judge.judge("q", "a2", CONTEXT) == second
    assert judge.calls == [("q", "a1"), ("q", "a2")]


def test_fake_judge_falls_back_to_default_once_the_script_is_exhausted() -> None:
    judge = FakeJudge(
        script=[JudgeVerdict(grounded=False, hallucination_detected=True, reasoning="x")]
    )

    judge.judge("q", "a1", CONTEXT)
    second = judge.judge("q", "a2", CONTEXT)

    assert second.grounded is True  # the built-in default
