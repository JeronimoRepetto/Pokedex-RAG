"""Add domain tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05 20:56:24.527981
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "abilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("effect_text", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "species",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("habitat", sa.String(length=50), nullable=True),
        sa.Column("capture_rate", sa.Integer(), nullable=True),
        sa.Column("is_legendary", sa.Boolean(), nullable=False),
        sa.Column("is_mythical", sa.Boolean(), nullable=False),
        sa.Column("evolution_chain_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_species_evolution_chain_id"), "species", ["evolution_chain_id"], unique=False
    )
    op.create_index(op.f("ix_species_generation"), "species", ["generation"], unique=False)
    op.create_table(
        "types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "evolutions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("from_species_id", sa.Integer(), nullable=False),
        sa.Column("to_species_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=50), nullable=True),
        sa.Column("min_level", sa.Integer(), nullable=True),
        sa.Column("item", sa.String(length=100), nullable=True),
        sa.Column(
            "conditions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["from_species_id"],
            ["species.id"],
        ),
        sa.ForeignKeyConstraint(
            ["to_species_id"],
            ["species.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_species_id", "to_species_id", name="uq_evolutions_edge"),
    )
    op.create_index(op.f("ix_evolutions_chain_id"), "evolutions", ["chain_id"], unique=False)
    op.create_index(
        op.f("ix_evolutions_from_species_id"), "evolutions", ["from_species_id"], unique=False
    )
    op.create_index(
        op.f("ix_evolutions_to_species_id"), "evolutions", ["to_species_id"], unique=False
    )
    op.create_table(
        "flavor_texts",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("species_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["species_id"],
            ["species.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("species_id", "version", "language", name="uq_flavor_texts_entry"),
    )
    op.create_index(
        op.f("ix_flavor_texts_species_id"), "flavor_texts", ["species_id"], unique=False
    )
    op.create_table(
        "moves",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=True),
        sa.Column("power", sa.Integer(), nullable=True),
        sa.Column("accuracy", sa.Integer(), nullable=True),
        sa.Column("pp", sa.Integer(), nullable=True),
        sa.Column("damage_class", sa.String(length=30), nullable=True),
        sa.Column("effect_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["types.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "pokemon",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("species_id", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("base_experience", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["species_id"],
            ["species.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_pokemon_species_id"), "pokemon", ["species_id"], unique=False)
    op.create_table(
        "pokemon_abilities",
        sa.Column("pokemon_id", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("ability_id", sa.Integer(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ability_id"],
            ["abilities.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
        ),
        sa.PrimaryKeyConstraint("pokemon_id", "slot"),
    )
    op.create_index(
        op.f("ix_pokemon_abilities_ability_id"), "pokemon_abilities", ["ability_id"], unique=False
    )
    op.create_table(
        "pokemon_moves",
        sa.Column("pokemon_id", sa.Integer(), nullable=False),
        sa.Column("move_id", sa.Integer(), nullable=False),
        sa.Column("learn_method", sa.String(length=30), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["move_id"],
            ["moves.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
        ),
        sa.PrimaryKeyConstraint("pokemon_id", "move_id", "learn_method", "level"),
    )
    op.create_table(
        "pokemon_stats",
        sa.Column("pokemon_id", sa.Integer(), nullable=False),
        sa.Column("stat_name", sa.String(length=30), nullable=False),
        sa.Column("base_value", sa.Integer(), nullable=False),
        sa.Column("effort", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
        ),
        sa.PrimaryKeyConstraint("pokemon_id", "stat_name"),
    )
    op.create_table(
        "pokemon_types",
        sa.Column("pokemon_id", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["types.id"],
        ),
        sa.PrimaryKeyConstraint("pokemon_id", "slot"),
    )
    op.create_index(op.f("ix_pokemon_types_type_id"), "pokemon_types", ["type_id"], unique=False)
    op.create_table(
        "sprites",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("pokemon_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pokemon_id", "kind", name="uq_sprites_pokemon_kind"),
    )
    op.create_index(op.f("ix_sprites_pokemon_id"), "sprites", ["pokemon_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sprites_pokemon_id"), table_name="sprites")
    op.drop_table("sprites")
    op.drop_index(op.f("ix_pokemon_types_type_id"), table_name="pokemon_types")
    op.drop_table("pokemon_types")
    op.drop_table("pokemon_stats")
    op.drop_table("pokemon_moves")
    op.drop_index(op.f("ix_pokemon_abilities_ability_id"), table_name="pokemon_abilities")
    op.drop_table("pokemon_abilities")
    op.drop_index(op.f("ix_pokemon_species_id"), table_name="pokemon")
    op.drop_table("pokemon")
    op.drop_table("moves")
    op.drop_index(op.f("ix_flavor_texts_species_id"), table_name="flavor_texts")
    op.drop_table("flavor_texts")
    op.drop_index(op.f("ix_evolutions_to_species_id"), table_name="evolutions")
    op.drop_index(op.f("ix_evolutions_from_species_id"), table_name="evolutions")
    op.drop_index(op.f("ix_evolutions_chain_id"), table_name="evolutions")
    op.drop_table("evolutions")
    op.drop_table("types")
    op.drop_index(op.f("ix_species_generation"), table_name="species")
    op.drop_index(op.f("ix_species_evolution_chain_id"), table_name="species")
    op.drop_table("species")
    op.drop_table("abilities")
