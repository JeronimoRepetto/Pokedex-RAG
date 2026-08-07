from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["intent"])


class IntentRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)  # same bounds as ChatRequest


class EntityOut(BaseModel):
    id: int
    name: str
    matched_text: str
    match: str
    score: float


class IntentResponse(BaseModel):
    intent: str  # card | question | compare
    entities: list[EntityOut] = []
    confidence: float
    method: str  # deterministic | llm | fallback
    warnings: list[str] = []


@router.post("/intent", response_model=IntentResponse)
def classify_intent(request: Request, body: IntentRequest) -> IntentResponse:
    """Classify what the user wants; the caller dispatches to the right endpoint.

    Deliberately cannot fail for a valid question: rule failures and classifier
    failures both degrade to `question`, because a broken classifier taking down the
    entrance to the app would be strictly worse than no classifier.
    """
    result = request.app.state.intent_service.resolve(body.question)
    return IntentResponse(
        intent=result.intent,
        entities=[EntityOut(**vars(entity)) for entity in result.entities],
        confidence=result.confidence,
        method=result.method,
        warnings=list(result.warnings),
    )
