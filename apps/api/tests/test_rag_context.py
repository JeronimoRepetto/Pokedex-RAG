import pytest

from api.rag.context import ContextDocument, build_context


def doc(document_id: int, content: str = "some content") -> ContextDocument:
    return ContextDocument(
        document_id=document_id,
        title=f"Doc {document_id}",
        content=content,
        pokemon_name="bulbasaur",
        doc_type="card",
    )


def test_numbers_documents_and_builds_citation_map() -> None:
    built = build_context([doc(10), doc(20)])

    assert "[1] Doc 10" in built.text
    assert "[2] Doc 20" in built.text
    assert built.citation_map[1].document_id == 10
    assert built.citation_map[2].document_id == 20
    assert built.markers == [1, 2]


def test_budget_cuts_lower_ranked_documents() -> None:
    built = build_context([doc(1, "x" * 300), doc(2, "y" * 300)], budget_chars=400)

    assert built.markers == [1]
    assert "Doc 2" not in built.text


def test_one_document_always_fits_truncated() -> None:
    built = build_context([doc(1, "z" * 5000)], budget_chars=500)

    assert built.markers == [1]
    assert len(built.text) <= 500
    assert built.text.endswith("…")


def test_tiny_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_context([doc(1)], budget_chars=50)
