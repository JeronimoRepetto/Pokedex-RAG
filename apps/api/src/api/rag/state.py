"""RAG graph state. Nodes read/write only their own keys; the parallel retrieval
branches write disjoint keys so LangGraph needs no custom reducers."""

from typing import Any, TypedDict

from api.rag.context import BuiltContext
from api.search import SearchHit


class RAGState(TypedDict, total=False):
    # inputs
    request_id: str
    question: str
    limit: int
    provider_override: str | None  # manual-comparison override for /chat (Phase 4.1)
    # retrieval
    normalized_question: str
    vector_hits: list[SearchHit]
    lexical_hits: list[SearchHit]
    fused_hits: list[SearchHit]
    # context
    context: BuiltContext | None
    # generation
    draft_answer: str
    provider: str
    model: str
    prompt_tokens: int
    output_tokens: int
    generation_metadata: dict[str, Any]
    # outcome
    status: str  # ResponseStatus values
    warnings: list[str]
    citations: list[dict[str, Any]]
    answer: str | None
    corrections_applied: int  # set by the validate node (Phase 5.4)
