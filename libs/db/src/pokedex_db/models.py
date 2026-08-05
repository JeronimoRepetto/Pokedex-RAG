"""SQLAlchemy models. Types use variants so unit tests can run on SQLite;
migrations only ever run against PostgreSQL."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

BigIntPK = BigInteger().with_variant(Integer(), "sqlite")
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class RawSnapshot(Base):
    """Immutable audit copy of one PokéAPI resource, fetched exactly once.

    The app never re-fetches at request time: this table (plus the file under data/raw/)
    is the reproducibility and provenance record for everything derived downstream.
    """

    __tablename__ = "raw_snapshots"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_raw_snapshots_resource"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    resource_type: Mapped[str] = mapped_column(String(50), index=True)
    resource_id: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONVariant)
    sha256: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
