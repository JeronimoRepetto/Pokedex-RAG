"""Response contracts shared across components (API responses, eval expectations)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ResponseStatus(StrEnum):
    ANSWERED = "answered"
    CORRECTED = "corrected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PROVIDER_ERROR = "provider_error"


class Citation(BaseModel):
    marker: int = Field(ge=1, description="The [n] marker used in the answer text")
    document_id: str
    source_url: str | None = None
    snippet: str | None = None


class RAGResponse(BaseModel):
    status: ResponseStatus
    answer: str | None = None
    citations: list[Citation] = []
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = []
    corrections_applied: int = Field(default=0, ge=0)
    evaluation_id: str | None = None
    request_id: str
