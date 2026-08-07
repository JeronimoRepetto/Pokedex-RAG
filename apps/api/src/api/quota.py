"""Daily spend ceiling for a public deployment.

The premise, stated plainly because it drives every choice here: **a browser cannot keep
a secret**. `NEXT_PUBLIC_API_KEY` is compiled into the bundle, so anyone can replay any
request from devtools. The goal is therefore not to hide credentials but to bound what
they can cost.

Enforcement sits around `LLMGateway.generate` rather than on the routers, because that
is the single place money is actually spent. Everything paid goes through it — /chat,
/compare, the judge, /intent escalation — and so will anything added later, which a
per-router check would silently miss. One `/compare` request can fan out to nine paid
calls; counting requests would undercount by ~9x.

The counter lives in PostgreSQL, not in memory: Cloud Run runs several instances, and an
in-process counter would let the real limit be (instances x limit).
"""

import hashlib
import logging
from collections.abc import Iterator
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from pokedex_db.models import ApiUsage
from pokedex_llm import GenerationRequest, GenerationResult

logger = logging.getLogger(__name__)

GLOBAL_BUCKET = "llm"


class QuotaExceededError(RuntimeError):
    """The daily allowance is spent. Carries both languages so the router can hand the
    UI a message it can show without translating anything itself."""

    detail_en = "The daily demo quota for AI answers has been reached. Try again tomorrow."
    detail_es = "Se alcanzó la cuota diaria de respuestas con IA. Volvé a intentarlo mañana."

    def __init__(self, bucket: str, limit: int) -> None:
        super().__init__(f"quota exceeded for {bucket!r} (limit {limit})")
        self.bucket = bucket
        self.limit = limit


def hash_caller(identifier: str) -> str:
    """Per-caller bucket key. The address is hashed and truncated, never stored: the
    counter only needs to tell callers apart, not identify them (guideline 7: no PII)."""
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"ip:{digest[:32]}"


class UsageCounter:
    """Atomic per-day counters in the database."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def current(self, bucket: str, today: date | None = None) -> int:
        with self._session_factory() as session:
            return self._read(session, bucket, today or date.today())

    def increment(self, bucket: str, today: date | None = None) -> int:
        """Increment and return the new value.

        UPDATE-then-INSERT rather than INSERT-then-catch: the row exists for all but the
        first call of the day, so the common path is a single statement.
        """
        day = today or date.today()
        with self._session_factory() as session:
            updated = session.execute(
                ApiUsage.__table__.update()
                .where(ApiUsage.day == day, ApiUsage.bucket == bucket)
                .values(count=ApiUsage.count + 1)
            ).rowcount
            if not updated:
                session.execute(ApiUsage.__table__.insert().values(day=day, bucket=bucket, count=1))
            session.commit()
            return self._read(session, bucket, day)

    @staticmethod
    def _read(session: Session, bucket: str, day: date) -> int:
        value = session.scalar(
            select(func.coalesce(ApiUsage.count, 0)).where(
                ApiUsage.day == day, ApiUsage.bucket == bucket
            )
        )
        return int(value or 0)


class QuotaGateway:
    """An LLMGateway that refuses to spend past the daily allowance.

    Satisfies the same Protocol as every adapter, so it composes with `_LazyGateway` and
    the provider registry without either knowing it exists.
    """

    def __init__(self, inner, counter: UsageCounter, daily_limit: int) -> None:
        self._inner = inner
        self._counter = counter
        self._daily_limit = daily_limit

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._charge()
        return self._inner.generate(request)

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        self._charge()
        return self._inner.stream(request)

    def _charge(self) -> None:
        if self._daily_limit <= 0:  # 0 or negative disables the ceiling (local dev)
            return
        used = self._counter.increment(GLOBAL_BUCKET)
        # Increment BEFORE checking: a call that is about to be refused has still been
        # counted, so a caller retrying in a loop cannot ride the boundary forever.
        if used > self._daily_limit:
            logger.warning(
                "daily LLM quota exceeded",
                extra={"used": used, "limit": self._daily_limit},
            )
            raise QuotaExceededError(GLOBAL_BUCKET, self._daily_limit)
