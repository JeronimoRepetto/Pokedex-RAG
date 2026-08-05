import pytest
from pydantic import ValidationError

from pokedex_common.contracts import Citation, RAGResponse, ResponseStatus


def test_full_response_roundtrip() -> None:
    response = RAGResponse(
        status=ResponseStatus.ANSWERED,
        answer="Bulbasaur is grass/poison [1].",
        citations=[Citation(marker=1, document_id="doc-bulbasaur-card")],
        confidence=0.91,
        corrections_applied=1,
        evaluation_id="eval-1",
        request_id="req-1",
    )

    payload = response.model_dump()
    assert payload["status"] == "answered"
    assert payload["citations"][0]["marker"] == 1


def test_abstention_needs_no_answer() -> None:
    response = RAGResponse(
        status=ResponseStatus.INSUFFICIENT_EVIDENCE,
        warnings=["no evidence found for the question"],
        request_id="req-2",
    )
    assert response.answer is None
    assert response.citations == []
    assert response.corrections_applied == 0


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_out_of_bounds_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        RAGResponse(status=ResponseStatus.ANSWERED, confidence=confidence, request_id="r")


def test_citation_marker_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Citation(marker=0, document_id="doc-1")


def test_status_values_match_api_contract() -> None:
    assert {status.value for status in ResponseStatus} == {
        "answered",
        "corrected",
        "insufficient_evidence",
        "provider_error",
    }
