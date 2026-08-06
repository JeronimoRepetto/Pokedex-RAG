"""Retrieval and prompt-building steps shared by the RAG graph and `/compare`.

These are the pieces that MUST be identical between the two entry points: if
`/compare` fused hits or built its prompt even slightly differently, the comparison
would measure the difference between two pipelines instead of between two models.
They live here as plain functions so both callers get the same behavior by
construction rather than by copy-paste (Phase 6.2).

The graph keeps its own parallel retrieve_vector ∥ retrieve_lexical branches;
`retrieve_hits` is the sequential equivalent for callers that aren't a graph.
"""

import re
from dataclasses import dataclass, field

from api.fusion import reciprocal_rank_fusion
from api.rag.context import BuiltContext, ContextDocument, build_context
from api.rag.prompts import INSUFFICIENT_EVIDENCE_SENTINEL, SYSTEM_PROMPT, USER_TEMPLATE
from api.search import SearchHit
from pokedex_llm import GenerationRequest, Message

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def normalize_question(question: str) -> str:
    return " ".join(question.split())


def fuse_hits(
    vector_hits: list[SearchHit], lexical_hits: list[SearchHit], limit: int
) -> list[SearchHit]:
    by_id: dict[int, SearchHit] = {hit.document_id: hit for hit in [*lexical_hits, *vector_hits]}
    fused = reciprocal_rank_fusion(
        [
            [hit.document_id for hit in vector_hits],
            [hit.document_id for hit in lexical_hits],
        ]
    )
    return [by_id[doc_id] for doc_id, _ in fused[:limit]]


def load_context(loader, hits: list[SearchHit], budget_chars: int) -> BuiltContext | None:
    if not hits:
        return None
    loaded: dict[int, ContextDocument] = loader.load([hit.document_id for hit in hits])
    ordered = [loaded[hit.document_id] for hit in hits if hit.document_id in loaded]
    return build_context(ordered, budget_chars)


def retrieve_hits(repository, embedder, normalized_question: str, limit: int) -> list[SearchHit]:
    """Sequential vector + lexical retrieval, fused — the graph's parallel branches
    produce the same fused list."""
    vector_hits = repository.vector_search(embedder.embed_query(normalized_question), limit)
    lexical_hits = repository.lexical_search(normalized_question, limit)
    return fuse_hits(vector_hits, lexical_hits, limit)


def build_generation_request(
    context: BuiltContext,
    normalized_question: str,
    *,
    max_output_tokens: int,
    judge_feedback: str | None = None,
) -> GenerationRequest:
    user_content = USER_TEMPLATE.format(context=context.text, question=normalized_question)
    if judge_feedback:
        user_content += (
            f"\n\nA fact-checker rejected your previous answer: {judge_feedback}. "
            "Answer again, more carefully, using ONLY the context documents above."
        )
    return GenerationRequest(
        messages=[
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ],
        temperature=0.2,
        max_output_tokens=max_output_tokens,
    )


@dataclass(frozen=True)
class FinalizedAnswer:
    """`warnings` holds only the warnings this step produced; callers merge them with
    whatever they already accumulated."""

    status: str
    answer: str | None
    citations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def finalize_answer(draft: str, context: BuiltContext) -> FinalizedAnswer:
    """Turn a raw model draft into a status + validated citation list.

    Abstention sentinel wins over everything; citation markers pointing outside the
    context are dropped and warned about rather than passed through to the caller.
    """
    draft = draft.strip()
    if draft.startswith(INSUFFICIENT_EVIDENCE_SENTINEL):
        detail = draft.removeprefix(INSUFFICIENT_EVIDENCE_SENTINEL).strip()
        return FinalizedAnswer(
            status="insufficient_evidence",
            answer=None,
            warnings=[f"model abstained: {detail}" if detail else "model abstained"],
        )
    markers = sorted({int(m) for m in CITATION_PATTERN.findall(draft)})
    valid = [m for m in markers if m in context.citation_map]
    invalid = [m for m in markers if m not in context.citation_map]
    warnings: list[str] = []
    if invalid:
        warnings.append(f"answer cited unknown documents: {invalid}")
    if not valid:
        warnings.append("answer contains no valid citations")
    citations = [
        {
            "marker": marker,
            "document_id": str(context.citation_map[marker].document_id),
            "source_url": next(
                iter(context.citation_map[marker].source_refs.get("pokeapi", [])), None
            ),
            "snippet": context.citation_map[marker].title,
        }
        for marker in valid
    ]
    return FinalizedAnswer(status="answered", answer=draft, citations=citations, warnings=warnings)
