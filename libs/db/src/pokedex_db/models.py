"""SQLAlchemy models. Types use variants so unit tests can run on SQLite;
migrations only ever run against PostgreSQL.

Domain ids reuse PokéAPI ids verbatim (pokemon.id, species.id, types.id, ...) so every
row stays traceable to its snapshot. Measurements keep PokéAPI units: height in
decimetres, weight in hectograms.
"""

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

BigIntPK = BigInteger().with_variant(Integer(), "sqlite")
JSONVariant = JSON().with_variant(JSONB(), "postgresql")

# Embedding column width. Changing it means a NEW space, a new table/partition and a new
# migration — never a silent edit (see embedding_spaces + startup verification).
VECTOR_DIMENSIONS = 768
# pgvector's Vector only compiles on PostgreSQL; SQLite unit tests store a JSON list.
VectorVariant = Vector(VECTOR_DIMENSIONS).with_variant(JSON(), "sqlite")


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


class Species(Base):
    __tablename__ = "species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # PokéAPI species id
    name: Mapped[str] = mapped_column(String(100), unique=True)
    generation: Mapped[int] = mapped_column(Integer, index=True)
    color: Mapped[str | None] = mapped_column(String(50))
    habitat: Mapped[str | None] = mapped_column(String(50))
    capture_rate: Mapped[int | None] = mapped_column(Integer)
    is_legendary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mythical: Mapped[bool] = mapped_column(Boolean, default=False)
    evolution_chain_id: Mapped[int | None] = mapped_column(Integer, index=True)


class Pokemon(Base):
    __tablename__ = "pokemon"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # PokéAPI pokemon id
    name: Mapped[str] = mapped_column(String(100), unique=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"), index=True)
    height: Mapped[int | None] = mapped_column(Integer)  # decimetres
    weight: Mapped[int | None] = mapped_column(Integer)  # hectograms
    base_experience: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)


class Type(Base):
    __tablename__ = "types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # PokéAPI type id
    name: Mapped[str] = mapped_column(String(50), unique=True)


class PokemonType(Base):
    __tablename__ = "pokemon_types"

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("types.id"), index=True)


class TypeEffectiveness(Base):
    """How much damage one attacking type deals to one defending type.

    ONLY non-neutral pairs are stored: a missing row means 1x. PokéAPI's
    `damage_relations` lists exactly the non-neutral relations, so storing the
    absences would mean inventing ~140 rows that carry no information — and the
    "no row = neutral" rule then lives in one documented place (`multiplier_for`)
    instead of being re-derived by every reader.
    """

    __tablename__ = "type_effectiveness"

    attacking_type_id: Mapped[int] = mapped_column(ForeignKey("types.id"), primary_key=True)
    defending_type_id: Mapped[int] = mapped_column(ForeignKey("types.id"), primary_key=True)
    # 2.0 super effective | 0.5 not very effective | 0.0 immune. Float, not Numeric:
    # these are exact binary fractions, so no precision is lost and arithmetic on
    # dual-type combinations stays trivial.
    multiplier: Mapped[float] = mapped_column(Float)


class Ability(Base):
    __tablename__ = "abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # PokéAPI ability id
    name: Mapped[str] = mapped_column(String(100), unique=True)
    effect_text: Mapped[str | None] = mapped_column(Text)


class PokemonAbility(Base):
    __tablename__ = "pokemon_abilities"

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    ability_id: Mapped[int] = mapped_column(ForeignKey("abilities.id"), index=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class PokemonStat(Base):
    __tablename__ = "pokemon_stats"

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), primary_key=True)
    stat_name: Mapped[str] = mapped_column(String(30), primary_key=True)  # hp, attack, ...
    base_value: Mapped[int] = mapped_column(Integer)
    effort: Mapped[int] = mapped_column(Integer, default=0)


class Move(Base):
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # PokéAPI move id
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type_id: Mapped[int | None] = mapped_column(ForeignKey("types.id"))
    power: Mapped[int | None] = mapped_column(Integer)
    accuracy: Mapped[int | None] = mapped_column(Integer)
    pp: Mapped[int | None] = mapped_column(Integer)
    damage_class: Mapped[str | None] = mapped_column(String(30))
    effect_text: Mapped[str | None] = mapped_column(Text)


class PokemonMove(Base):
    __tablename__ = "pokemon_moves"

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), primary_key=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("moves.id"), primary_key=True)
    learn_method: Mapped[str] = mapped_column(String(30), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)


class Evolution(Base):
    """One evolution edge (from -> to) with its trigger conditions.

    Extra condition details beyond the common trigger/min_level/item stay in
    `conditions` verbatim (JSON), so nothing from the chain payload is lost.
    """

    __tablename__ = "evolutions"
    __table_args__ = (
        UniqueConstraint("from_species_id", "to_species_id", name="uq_evolutions_edge"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(Integer, index=True)
    from_species_id: Mapped[int] = mapped_column(ForeignKey("species.id"), index=True)
    to_species_id: Mapped[int] = mapped_column(ForeignKey("species.id"), index=True)
    trigger: Mapped[str | None] = mapped_column(String(50))
    min_level: Mapped[int | None] = mapped_column(Integer)
    item: Mapped[str | None] = mapped_column(String(100))
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)


class FlavorText(Base):
    __tablename__ = "flavor_texts"
    __table_args__ = (
        UniqueConstraint("species_id", "version", "language", name="uq_flavor_texts_entry"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)


class EmbeddingSpace(Base):
    """One vector space = one embedding model at one dimensionality.

    Every embedding row is FK-bound to a space, every query filters by space, and each
    component verifies at startup that its configured space matches this row — so
    vectors from different models can never be compared (ADR-0002 layering).
    """

    __tablename__ = "embedding_spaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(100), unique=True)  # e.g. gemini-embedding-2-768-v1
    model_name: Mapped[str] = mapped_column(String(100))
    dimensions: Mapped[int] = mapped_column(Integer)
    modality: Mapped[str] = mapped_column(String(30))  # text | multimodal
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    """Deterministically-built RAG document for one Pokémon (card/flavor/moves/evolution).

    `content_hash` lets the embed job skip unchanged content. A PostgreSQL-only
    generated tsvector column (`content_tsv`, migration 0003) backs lexical search and
    is intentionally unmapped here so SQLite unit tests keep working.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("pokemon_id", "doc_type", name="uq_documents_pokemon_doctype"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(String(30))  # card | flavor | moves | evolution
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_refs: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("space_id", "object_type", "object_id", name="uq_embeddings_object"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("embedding_spaces.id"), index=True)
    object_type: Mapped[str] = mapped_column(String(20))  # document | sprite
    object_id: Mapped[int] = mapped_column(BigInteger)
    embedding: Mapped[list[float]] = mapped_column(VectorVariant)
    content_hash: Mapped[str] = mapped_column(String(64))  # hash of the embedded content
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagAnswer(Base):
    """One /chat interaction: the mining ground for regression cases (Phase 5)."""

    __tablename__ = "rag_answers"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))  # ResponseStatus values
    answer: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONVariant, default=list)
    confidence: Mapped[float | None] = mapped_column()
    warnings: Mapped[list] = mapped_column(JSONVariant, default=list)
    corrections_applied: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    """One `evals run` invocation — the container for its per-case `EvalResult` rows."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    suite: Mapped[str] = mapped_column(String(50), index=True)
    api_base_url: Mapped[str] = mapped_column(Text)
    case_count: Mapped[int] = mapped_column(Integer)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)  # suite-level means
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalResult(Base):
    """One golden case's score within one `EvalRun` — the mining ground for
    Phase 5.7's regression capture (`evals add-regression --answer-id ...`)."""

    __tablename__ = "eval_results"
    __table_args__ = (UniqueConstraint("run_id", "case_id", name="uq_eval_results_run_case"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(100), index=True)
    retrieved_ids: Mapped[list] = mapped_column(JSONVariant, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiUsage(Base):
    """Daily counters that bound what a public deployment can spend.

    Deliberately NOT derived from `rag_answers`: that table misses judge calls,
    reformulate retries, /intent escalation and every embedding, while adding rows for
    /chat requests where no model ran. This one is incremented at the single place a
    paid call actually happens.

    `bucket` is either the global `llm` counter or `ip:<sha256 prefix>` — the address
    itself is never stored, so the table holds no personal data.
    """

    __tablename__ = "api_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(80), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Sprite(Base):
    """Manifest of downloaded sprite files. The image bytes live under data/ (never in
    git); this row records provenance and integrity."""

    __tablename__ = "sprites"
    __table_args__ = (UniqueConstraint("pokemon_id", "kind", name="uq_sprites_pokemon_kind"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))  # default, shiny, official-artwork, ...
    source_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    license_note: Mapped[str] = mapped_column(
        Text,
        default="Images © The Pokémon Company; fetched via PokeAPI/sprites for educational use.",
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
