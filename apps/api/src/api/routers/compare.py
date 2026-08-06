from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pokedex_common.contracts import Citation
from pokedex_common.request_id import get_request_id, new_request_id
from pokedex_embeddings import EmbeddingError, SpaceMismatchError

router = APIRouter(tags=["rag"])

MAX_PROVIDERS = 4


class CompareRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    providers: list[str] | None = Field(
        default=None,
        description="Providers to compare (2-4, distinct). Defaults to LLM_PRIMARY + LLM_FALLBACK.",
    )


class JudgeVerdictOut(BaseModel):
    grounded: bool
    hallucination_detected: bool
    reasoning: str
    independent: bool


class CandidateOut(BaseModel):
    provider: str
    model: str
    status: str
    answer: str | None = None
    citations: list[Citation] = []
    warnings: list[str] = []
    corrections_applied: int = 0
    judge: JudgeVerdictOut | None = None
    latency_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0


class CompareResponse(BaseModel):
    question: str
    request_id: str
    context_document_ids: list[int] = []
    context_chars: int = 0
    candidates: list[CandidateOut] = []


def _resolve_providers(request: Request, requested: list[str] | None) -> list[str]:
    settings = request.app.state.settings
    known = request.app.state.provider_registry.known_providers()
    if requested is None:
        requested = [p for p in (settings.llm_primary, settings.llm_fallback) if p]
        if len(requested) < 2:
            raise HTTPException(
                status_code=422,
                detail=(
                    "no default provider pair is configured (LLM_PRIMARY + LLM_FALLBACK); "
                    f"pass `providers` explicitly. Known providers: {known}"
                ),
            )
    if len(requested) < 2:
        raise HTTPException(status_code=422, detail="comparing needs at least 2 providers")
    if len(requested) > MAX_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"at most {MAX_PROVIDERS} providers per comparison, got {len(requested)}",
        )
    if len(set(requested)) != len(requested):
        raise HTTPException(
            status_code=422,
            detail=(
                "providers must be distinct — a model compared against itself "
                f"proves nothing: {requested}"
            ),
        )
    unknown = [p for p in requested if p not in known]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"unknown provider(s) {unknown}; known: {known}"
        )
    return requested


@router.post("/compare", response_model=CompareResponse)
def compare(request: Request, body: CompareRequest) -> CompareResponse:
    """Same question, same retrieved context, N providers, each judged."""
    providers = _resolve_providers(request, body.providers)
    request_id = get_request_id() or new_request_id()
    try:
        result = request.app.state.compare_service.compare(body.question, providers, request_id)
    except SpaceMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CompareResponse(
        question=result.question,
        request_id=result.request_id,
        context_document_ids=result.context_document_ids,
        context_chars=result.context_chars,
        candidates=[
            CandidateOut(
                provider=c.provider,
                model=c.model,
                status=c.status,
                answer=c.answer,
                citations=[Citation(**citation) for citation in c.citations],
                warnings=c.warnings,
                corrections_applied=c.corrections_applied,
                judge=JudgeVerdictOut(**vars(c.judge)) if c.judge else None,
                latency_ms=c.latency_ms,
                prompt_tokens=c.prompt_tokens,
                output_tokens=c.output_tokens,
            )
            for c in result.candidates
        ],
    )
