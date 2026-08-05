import pytest

from pokedex_llm import FakeLLM, GenerationRequest, Message, TransientProviderError


def request_for(text: str) -> GenerationRequest:
    return GenerationRequest(messages=[Message(role="user", content=text)])


def test_scripted_responses_come_out_in_order() -> None:
    fake = FakeLLM(script=["first", "second"])

    assert fake.generate(request_for("a")).text == "first"
    assert fake.generate(request_for("b")).text == "second"
    assert fake.generate(request_for("c")).text == "fake answer"  # default afterwards


def test_exception_items_are_raised() -> None:
    fake = FakeLLM(script=[TransientProviderError("boom"), "recovered"])

    with pytest.raises(TransientProviderError):
        fake.generate(request_for("a"))
    assert fake.generate(request_for("b")).text == "recovered"


def test_requests_are_recorded_for_assertions() -> None:
    fake = FakeLLM()

    fake.generate(request_for("what beats squirtle?"))

    assert fake.requests[0].messages[0].content == "what beats squirtle?"
