"""The RAG pipeline as a LangGraph graph.

    analyze_query → (retrieve_vector ∥ retrieve_lexical) → fuse_rrf
                  → build_context → generate → finalize → validate → judge
                  → (conditional: END | reformulate → generate | abstain → END)

Dependencies (repository, embedder, gateway, document loader) are injected via
`RagDeps` when the graph is built, so the whole graph runs on fakes in unit tests.
Phase 4 added the provider-fallback branch; 5.4 added deterministic validation; 5.5
adds the judge + its conditional reformulate/abstain routing.
"""

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from langgraph.graph import END, START, StateGraph

from api.fusion import reciprocal_rank_fusion
from api.rag.context import BuiltContext, ContextDocument, build_context
from api.rag.judge import JudgeProtocol
from api.rag.prompts import (
    INSUFFICIENT_EVIDENCE_SENTINEL,
    SYSTEM_PROMPT,
    USER_TEMPLATE,
)
from api.rag.state import RAGState
from api.rag.validation import PokemonTypeLookupProtocol, check_type_claims
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
    fallback_provider: str | None = None  # tried once if the default gateway errors
    type_lookup: PokemonTypeLookupProtocol | None = None  # Phase 5.4 factual cross-check
    judge: JudgeProtocol | None = None  # Phase 5.5, a model DIFFERENT from `gateway`
    max_attempts: int = 2  # reformulate loop bound


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

    def resolve_fallback() -> LLMGateway:
        if deps.provider_registry is None:
            raise UnknownProviderError(
                f"fallback provider {deps.fallback_provider!r} configured but no registry is set"
            )
        return deps.provider_registry.build(deps.fallback_provider)

    def generate(state: RAGState) -> dict:
        context: BuiltContext | None = state.get("context")
        if context is None or not context.citation_map:
            return {
                "status": "insufficient_evidence",
                "warnings": ["retrieval returned no usable documents"],
                "draft_answer": "",
            }
        override = state.get("provider_override")
        gateway = resolve_gateway(state)
        user_content = USER_TEMPLATE.format(
            context=context.text, question=state["normalized_question"]
        )
        if state.get("attempt", 1) > 1 and state.get("judge_reasoning"):
            user_content += (
                f"\n\nA fact-checker rejected your previous answer: "
                f"{state['judge_reasoning']}. Answer again, more carefully, using ONLY "
                "the context documents above."
            )
        request = GenerationRequest(
            messages=[
                Message(role="system", content=SYSTEM_PROMPT),
                Message(role="user", content=user_content),
            ],
            temperature=0.2,
            max_output_tokens=deps.max_output_tokens,
        )
        warnings: list[str] = []
        try:
            result = gateway.generate(request)
        except (TransientProviderError, PermanentProviderError) as primary_exc:
            logger.error(
                "generation failed",
                extra={"provider": gateway.provider_name, "error": str(primary_exc)},
            )
            # A manual provider override is an explicit request for that provider;
            # only the default path falls back automatically, and only once.
            if override or not deps.fallback_provider:
                return {
                    "status": "provider_error",
                    "warnings": [f"generation failed: {primary_exc}"],
                    "draft_answer": "",
                    "provider": gateway.provider_name,
                    "model": gateway.model_name,
                }
            warnings.append(f"{gateway.provider_name} failed, falling back: {primary_exc}")
            gateway = resolve_fallback()
            try:
                result = gateway.generate(request)
            except (TransientProviderError, PermanentProviderError) as fallback_exc:
                logger.error(
                    "fallback generation failed",
                    extra={"provider": gateway.provider_name, "error": str(fallback_exc)},
                )
                return {
                    "status": "provider_error",
                    "warnings": [*warnings, f"fallback also failed: {fallback_exc}"],
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
            "warnings": warnings,
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

    def validate(state: RAGState) -> dict:
        if state.get("status") != "answered" or deps.type_lookup is None:
            return {}
        context: BuiltContext = state["context"]
        corrections = check_type_claims(state["answer"], context.citation_map, deps.type_lookup)
        if not corrections:
            return {}
        notes = " ".join(c.note() for c in corrections)
        return {
            "status": "corrected",
            "answer": f"{state['answer']}\n\n{notes}",
            "corrections_applied": len(corrections),
        }

    def judge_node(state: RAGState) -> dict:
        if state.get("status") not in ("answered", "corrected") or deps.judge is None:
            return {}
        context: BuiltContext = state["context"]
        try:
            verdict = deps.judge.judge(state["normalized_question"], state["answer"], context)
        except Exception as exc:  # a broken judge must never take down /chat itself
            logger.error("judge failed", extra={"error": str(exc)})
            return {
                "judge_grounded": True,
                "warnings": [*state.get("warnings", []), f"judge failed, assuming grounded: {exc}"],
            }
        warnings = list(state.get("warnings", []))
        if not verdict.grounded:
            warnings.append(f"judge flagged ungrounded answer: {verdict.reasoning}")
        return {
            "judge_grounded": verdict.grounded,
            "judge_reasoning": verdict.reasoning,
            "warnings": warnings,
        }

    def route_after_judge(state: RAGState) -> str:
        if deps.judge is None or state.get("judge_grounded", True):
            return "end"
        if state.get("attempt", 1) < deps.max_attempts:
            return "reformulate"
        return "abstain"

    def reformulate(state: RAGState) -> dict:
        return {"attempt": state.get("attempt", 1) + 1}

    def abstain(state: RAGState) -> dict:
        return {
            "status": "insufficient_evidence",
            "answer": None,
            "citations": [],
            "warnings": [
                *state.get("warnings", []),
                f"abstained after {state.get('attempt', 1)} attempt(s) rejected by the judge",
            ],
        }

    graph = StateGraph(RAGState)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("retrieve_vector", retrieve_vector)
    graph.add_node("retrieve_lexical", retrieve_lexical)
    graph.add_node("fuse_rrf", fuse_rrf)
    graph.add_node("build_context", build_context_node)
    graph.add_node("generate", generate)
    graph.add_node("finalize", finalize)
    graph.add_node("validate", validate)
    graph.add_node("judge", judge_node)
    graph.add_node("reformulate", reformulate)
    graph.add_node("abstain", abstain)

    graph.add_edge(START, "analyze_query")
    graph.add_edge("analyze_query", "retrieve_vector")
    graph.add_edge("analyze_query", "retrieve_lexical")
    graph.add_edge(["retrieve_vector", "retrieve_lexical"], "fuse_rrf")
    graph.add_edge("fuse_rrf", "build_context")
    graph.add_edge("build_context", "generate")
    graph.add_edge("generate", "finalize")
    graph.add_edge("finalize", "validate")
    graph.add_edge("validate", "judge")
    graph.add_conditional_edges(
        "judge", route_after_judge, {"end": END, "reformulate": "reformulate", "abstain": "abstain"}
    )
    graph.add_edge("reformulate", "generate")
    graph.add_edge("abstain", END)
    return graph.compile()
