"""Add translation cache table for trip previews

Revision ID: 010_translation_cache
Revises: 009_trip_language_translation
Create Date: 2025-02-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "010_translation_cache"
down_revision = "009_trip_language_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trip_translation_caches table
    op.create_table(
        "trip_translation_caches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        # Translated content
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description_short", sa.Text(), nullable=True),
        sa.Column("highlights", JSONB, nullable=True),
        sa.Column("inclusions", JSONB, nullable=True),
        sa.Column("exclusions", JSONB, nullable=True),
        sa.Column("info_general", sa.Text(), nullable=True),
        sa.Column("info_formalities", sa.Text(), nullable=True),
        sa.Column("info_booking_conditions", sa.Text(), nullable=True),
        sa.Column("info_cancellation_policy", sa.Text(), nullable=True),
        sa.Column("info_additional", sa.Text(), nullable=True),
        sa.Column("translated_days", JSONB, nullable=True),
        # Cache metadata
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # Primary key
        sa.PrimaryKeyConstraint("id"),
        # Foreign keys
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
    )

    # Create indexes
    op.create_index(
        "ix_trip_translation_caches_trip_language",
        "trip_translation_caches",
        ["trip_id", "language"],
        unique=True,
    )
    op.create_index(
        "ix_trip_translation_caches_is_stale",
        "trip_translation_caches",
        ["trip_id", "is_stale"],
    )
    op.create_index(
        "ix_trip_translation_caches_tenant_id",
        "trip_translation_caches",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trip_translation_caches_tenant_id", table_name="trip_translation_caches")
    op.drop_index("ix_trip_translation_caches_is_stale", table_name="trip_translation_caches")
    op.drop_index("ix_trip_translation_caches_trip_language", table_name="trip_translation_caches")
    op.drop_table("trip_translation_caches")
