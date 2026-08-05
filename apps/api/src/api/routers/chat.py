from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pokedex_common.contracts import RAGResponse
from pokedex_common.request_id import get_request_id, new_request_id
from pokedex_embeddings import SpaceMismatchError

router = APIRouter(tags=["rag"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/chat", response_model=RAGResponse)
def chat(request: Request, body: ChatRequest) -> RAGResponse:
    request_id = get_request_id() or new_request_id()
    try:
        return request.app.state.chat_service.ask(body.question, request_id)
    except SpaceMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
