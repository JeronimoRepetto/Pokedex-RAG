"""Chat service: run the graph, persist the interaction, return the API contract."""

import logging
import time

from sqlalchemy.orm import Session, sessionmaker

from api.rag.prompts import PROMPT_VERSION
from pokedex_common.contracts import Citation, RAGResponse, ResponseStatus
from pokedex_db.models import RagAnswer

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, graph, session_factory: sessionmaker[Session]) -> None:
        self._graph = graph
        self._session_factory = session_factory

    def ask(self, question: str, request_id: str, callbacks: list | None = None) -> RAGResponse:
        started = time.perf_counter()
        config = {"callbacks": callbacks} if callbacks else {}
        state = self._graph.invoke({"question": question, "request_id": request_id}, config=config)
        latency_ms = round((time.perf_counter() - started) * 1000)

        citations = [Citation(**c) for c in state.get("citations", [])]
        response = RAGResponse(
            status=ResponseStatus(state.get("status", "provider_error")),
            answer=state.get("answer"),
            citations=citations,
            confidence=None,  # the Phase-5 judge owns confidence
            warnings=state.get("warnings", []),
            corrections_applied=0,
            evaluation_id=None,
            request_id=request_id,
        )
        self._persist(question, state, response, latency_ms)
        return response

    def _persist(self, question: str, state: dict, response: RAGResponse, latency_ms: int) -> None:
        with self._session_factory() as session:
            session.add(
                RagAnswer(
                    request_id=response.request_id,
                    question=question,
                    status=response.status.value,
                    answer=response.answer,
                    citations=[c.model_dump() for c in response.citations],
                    confidence=response.confidence,
                    warnings=response.warnings,
                    corrections_applied=response.corrections_applied,
                    provider=state.get("provider"),
                    model=state.get("model"),
                    prompt_version=PROMPT_VERSION,
                    prompt_tokens=state.get("prompt_tokens", 0),
                    output_tokens=state.get("output_tokens", 0),
                    latency_ms=latency_ms,
                    langfuse_trace_id=None,
                )
            )
            session.commit()
        logger.info(
            "chat answered",
            extra={
                "status": response.status.value,
                "latency_ms": latency_ms,
                "citations": len(response.citations),
                "provider": state.get("provider"),
            },
        )
