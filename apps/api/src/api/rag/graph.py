"""The RAG pipeline as a LangGraph graph (deliberately linear in Phase 3).

    analyze_query → (retrieve_vector ∥ retrieve_lexical) → fuse_rrf
                  → build_context → generate → finalize

Dependencies (repository, embedder, gateway, document loader) are injected via
`RagDeps` when the graph is built, so the whole graph runs on fakes in unit tests.
Phase 4 adds the provider-fallback branch; Phase 5 adds validation/judge/reformulate.
"""

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from langgraph.graph import END, START, StateGraph

from api.fusion import reciprocal_rank_fusion
from api.rag.context import BuiltContext, ContextDocument, build_context
from api.rag.prompts import (
    INSUFFICIENT_EVIDENCE_SENTINEL,
    SYSTEM_PROMPT,
    USER_TEMPLATE,
)
from api.rag.state import RAGState
from api.search import SearchHit, SearchRepositoryProtocol
from pokedex_embeddings import EmbedderProtocol
from pokedex_llm import (
    GenerationRequest,
    LLMGateway,
    Message,
    PermanentProviderError,
    ProviderRegistry,
    TransientProviderError,
    UnknownProviderError,
)

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


class DocumentLoaderProtocol(Protocol):
    def load(self, document_ids: list[int]) -> dict[int, ContextDocument]: ...


@dataclass
class RagDeps:
    repository: SearchRepositoryProtocol
    embedder: EmbedderProtocol
    gateway: LLMGateway
    document_loader: DocumentLoaderProtocol
    retrieval_limit: int = 8
    context_budget_chars: int = 12_000
    max_output_tokens: int = 2048  # thinking models spend reasoning tokens from this
    provider_registry: ProviderRegistry | None = None  # resolves provider_override


def build_graph(deps: RagDeps):
    def analyze_query(state: RAGState) -> dict:
        return {"normalized_question": " ".join(state["question"].split())}

    def retrieve_vector(state: RAGState) -> dict:
        vector = deps.embedder.embed_texts([state["normalized_question"]])[0]
        return {"vector_hits": deps.repository.vector_search(vector, deps.retrieval_limit)}

    def retrieve_lexical(state: RAGState) -> dict:
        return {
            "lexical_hits": deps.repository.lexical_search(
                state["normalized_question"], deps.retrieval_limit
            )
        }

    def fuse_rrf(state: RAGState) -> dict:
        vector_hits = state.get("vector_hits", [])
        lexical_hits = state.get("lexical_hits", [])
        by_id: dict[int, SearchHit] = {
            hit.document_id: hit for hit in [*lexical_hits, *vector_hits]
        }
        fused = reciprocal_rank_fusion(
            [
                [hit.document_id for hit in vector_hits],
                [hit.document_id for hit in lexical_hits],
            ]
        )
        return {"fused_hits": [by_id[doc_id] for doc_id, _ in fused[: deps.retrieval_limit]]}

    def build_context_node(state: RAGState) -> dict:
        fused = state.get("fused_hits", [])
        if not fused:
            return {"context": None}
        loaded = deps.document_loader.load([hit.document_id for hit in fused])
        ordered = [loaded[hit.document_id] for hit in fused if hit.document_id in loaded]
        return {"context": build_context(ordered, deps.context_budget_chars)}

    def resolve_gateway(state: RAGState) -> LLMGateway:
        override = state.get("provider_override")
        if not override:
            return deps.gateway
        if deps.provider_registry is None:
            raise UnknownProviderError(
                f"provider override {override!r} requested but no registry is configured"
            )
        return deps.provider_registry.build(override)

    def generate(state: RAGState) -> dict:
        context: BuiltContext | None = state.get("context")
        if context is None or not context.citation_map:
            return {
                "status": "insufficient_evidence",
                "warnings": ["retrieval returned no usable documents"],
                "draft_answer": "",
            }
        gateway = resolve_gateway(state)
        request = GenerationRequest(
            messages=[
                Message(role="system", content=SYSTEM_PROMPT),
                Message(
                    role="user",
                    content=USER_TEMPLATE.format(
                        context=context.text, question=state["normalized_question"]
                    ),
                ),
            ],
            temperature=0.2,
            max_output_tokens=deps.max_output_tokens,
        )
        try:
            result = gateway.generate(request)
        except (TransientProviderError, PermanentProviderError) as exc:
            logger.error("generation failed", extra={"error": str(exc)})
            return {
                "status": "provider_error",
                "warnings": [f"generation failed: {exc}"],
                "draft_answer": "",
                "provider": gateway.provider_name,
                "model": gateway.model_name,
            }
        return {
            "draft_answer": result.text,
            "provider": result.provider,
            "model": result.model,
            "prompt_tokens": result.usage.prompt_tokens,
            "output_tokens": result.usage.output_tokens,
            "generation_metadata": result.metadata,
        }

    def finalize(state: RAGState) -> dict:
        if state.get("status") in ("insufficient_evidence", "provider_error"):
            return {"answer": None, "citations": []}
        draft = state.get("draft_answer", "").strip()
        context: BuiltContext = state["context"]
        if draft.startswith(INSUFFICIENT_EVIDENCE_SENTINEL):
            detail = draft.removeprefix(INSUFFICIENT_EVIDENCE_SENTINEL).strip()
            return {
                "status": "insufficient_evidence",
                "answer": None,
                "citations": [],
                "warnings": [
                    *state.get("warnings", []),
                    f"model abstained: {detail}" if detail else "model abstained",
                ],
            }
        markers = sorted({int(m) for m in CITATION_PATTERN.findall(draft)})
        warnings = list(state.get("warnings", []))
        valid = [m for m in markers if m in context.citation_map]
        invalid = [m for m in markers if m not in context.citation_map]
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
        return {"status": "answered", "answer": draft, "citations": citations, "warnings": warnings}

    graph = StateGraph(RAGState)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("retrieve_vector", retrieve_vector)
    graph.add_node("retrieve_lexical", retrieve_lexical)
    graph.add_node("fuse_rrf", fuse_rrf)
    graph.add_node("build_context", build_context_node)
    graph.add_node("generate", generate)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "analyze_query")
    graph.add_edge("analyze_query", "retrieve_vector")
    graph.add_edge("analyze_query", "retrieve_lexical")
    graph.add_edge(["retrieve_vector", "retrieve_lexical"], "fuse_rrf")
    graph.add_edge("fuse_rrf", "build_context")
    graph.add_edge("build_context", "generate")
    graph.add_edge("generate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
