"""Side-by-side provider comparison (Phase 6.2).

Retrieval runs ONCE and the resulting `GenerationRequest` object is reused verbatim for
every provider, so the only variable between candidates is the model itself. Each
candidate then goes through the same finalize → validate → judge steps `/chat` uses,
minus the reformulate loop: a comparison wants each model's first answer, not its
best-of-N.

One provider failing does not fail the comparison — that candidate comes back with
`status=provider_error` and the others still answer, because "provider A was down" is
itself a comparison result worth seeing.
"""

import logging
import time
from dataclasses import asdict, dataclass, field

from api.rag.graph import RagDeps
from api.rag.pipeline import (
    build_generation_request,
    finalize_answer,
    load_context,
    normalize_question,
    retrieve_hits,
)
from api.rag.prompts import PROMPT_VERSION
from api.rag.validation import check_type_claims
from pokedex_db.models import RagAnswer
from pokedex_llm import PermanentProviderError, TransientProviderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JudgeSummary:
    grounded: bool
    hallucination_detected: bool
    reasoning: str
    # False when the judge and this candidate are the same provider: the verdict is
    # still reported, but it is a model grading its own homework — not independent.
    independent: bool = True


@dataclass(frozen=True)
class CompareCandidate:
    provider: str
    model: str
    status: str
    answer: str | None = None
    citations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    corrections_applied: int = 0
    judge: JudgeSummary | None = None
    latency_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ComparisonResult:
    question: str
    request_id: str
    # The proof that the comparison was fair: one context, listed explicitly.
    context_document_ids: list[int] = field(default_factory=list)
    context_chars: int = 0
    candidates: list[CompareCandidate] = field(default_factory=list)


class CompareService:
    def __init__(
        self,
        deps: RagDeps,
        session_factory,
        *,
        judge_provider: str | None = None,
    ) -> None:
        self._deps = deps
        self._session_factory = session_factory
        self._judge_provider = judge_provider

    def compare(self, question: str, providers: list[str], request_id: str) -> ComparisonResult:
        deps = self._deps
        normalized = normalize_question(question)
        hits = retrieve_hits(deps.repository, deps.embedder, normalized, deps.retrieval_limit)
        context = load_context(deps.document_loader, hits, deps.context_budget_chars)

        if context is None or not context.citation_map:
            # No context: every model would be guessing. Say so without spending a
            # single generation call.
            return ComparisonResult(
                question=question,
                request_id=request_id,
                candidates=[
                    CompareCandidate(
                        provider=name,
                        model="",
                        status="insufficient_evidence",
                        warnings=["retrieval returned no usable documents"],
                    )
                    for name in providers
                ],
            )

        request = build_generation_request(
            context, normalized, max_output_tokens=deps.max_output_tokens
        )
        candidates = [self._run_candidate(name, request, normalized, context) for name in providers]
        self._persist(question, request_id, candidates)
        logger.info(
            "comparison finished",
            extra={
                "providers": providers,
                "context_documents": len(context.citation_map),
                "statuses": [c.status for c in candidates],
            },
        )
        return ComparisonResult(
            question=question,
            request_id=request_id,
            context_document_ids=[doc.document_id for doc in context.citation_map.values()],
            context_chars=len(context.text),
            candidates=candidates,
        )

    def _run_candidate(self, name, request, normalized_question, context) -> CompareCandidate:
        deps = self._deps
        gateway = deps.provider_registry.build(name)
        started = time.perf_counter()
        try:
            result = gateway.generate(request)
        except (TransientProviderError, PermanentProviderError) as exc:
            logger.error("comparison candidate failed", extra={"provider": name, "error": str(exc)})
            return CompareCandidate(
                provider=name,
                model=gateway.model_name,
                status="provider_error",
                warnings=[f"generation failed: {exc}"],
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        latency_ms = round((time.perf_counter() - started) * 1000)

        finalized = finalize_answer(result.text, context)
        status, answer = finalized.status, finalized.answer
        warnings = list(finalized.warnings)
        corrections = 0
        if status == "answered" and deps.type_lookup is not None:
            found = check_type_claims(answer, context.citation_map, deps.type_lookup)
            if found:
                status = "corrected"
                answer = f"{answer}\n\n{' '.join(c.note() for c in found)}"
                corrections = len(found)

        judge_summary = None
        if deps.judge is not None and status in ("answered", "corrected"):
            judge_summary, judge_warning = self._judge(name, normalized_question, answer, context)
            if judge_warning:
                warnings.append(judge_warning)

        return CompareCandidate(
            provider=result.provider,
            model=result.model,
            status=status,
            answer=answer,
            citations=finalized.citations,
            warnings=warnings,
            corrections_applied=corrections,
            judge=judge_summary,
            latency_ms=latency_ms,
            prompt_tokens=result.usage.prompt_tokens,
            output_tokens=result.usage.output_tokens,
        )

    def _judge(self, provider_name, question, answer, context):
        """Returns (summary or None, warning or None). A broken judge degrades the
        comparison to 'unjudged' rather than taking it down."""
        independent = self._judge_provider != provider_name
        try:
            verdict = self._deps.judge.judge(question, answer, context)
        except Exception as exc:
            logger.error(
                "comparison judge failed", extra={"provider": provider_name, "error": str(exc)}
            )
            return None, f"judge failed, candidate left unjudged: {exc}"
        warning = None
        if not independent:
            warning = (
                f"judge provider is {provider_name!r}, the same model that produced this "
                "answer — verdict is not independent"
            )
        elif not verdict.grounded:
            warning = f"judge flagged ungrounded answer: {verdict.reasoning}"
        return (
            JudgeSummary(
                grounded=verdict.grounded,
                hallucination_detected=verdict.hallucination_detected,
                reasoning=verdict.reasoning,
                independent=independent,
            ),
            warning,
        )

    def _persist(self, question: str, request_id: str, candidates: list[CompareCandidate]) -> None:
        """Every candidate is a real answer, so it lands in rag_answers like any /chat
        interaction — which makes comparison answers minable by `evals add-regression`
        too. They share one request_id and are told apart by provider."""
        with self._session_factory() as session:
            for candidate in candidates:
                session.add(
                    RagAnswer(
                        request_id=request_id,
                        question=question,
                        status=candidate.status,
                        answer=candidate.answer,
                        citations=candidate.citations,
                        confidence=None,
                        warnings=candidate.warnings,
                        corrections_applied=candidate.corrections_applied,
                        provider=candidate.provider,
                        model=candidate.model,
                        prompt_version=PROMPT_VERSION,
                        prompt_tokens=candidate.prompt_tokens,
                        output_tokens=candidate.output_tokens,
                        latency_ms=candidate.latency_ms,
                    )
                )
            session.commit()


def candidate_as_dict(candidate: CompareCandidate) -> dict:
    return asdict(candidate)
