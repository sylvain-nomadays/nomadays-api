"""Add distribution fields for B2B syndication

Revision ID: 008_distribution_fields
Revises: 007_trip_categories
Create Date: 2024-02-06

Adds fields for distributing circuits to partner platforms:
- is_distributable: Whether this circuit can be syndicated
- distribution_channels: JSON array of authorized channels
- external_reference: External ID for partners
- pricing_rules_json: Pricing rules per distribution channel
- source_url: URL source if imported from external site
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "008_distribution_fields"
down_revision = "007_trip_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Distribution fields
    op.add_column(
        "trips",
        sa.Column("is_distributable", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "trips",
        sa.Column("distribution_channels", JSONB, nullable=True),
        # Example: ["nomadays.com", "partner1.com", "comparateur.fr"]
    )
    op.add_column(
        "trips",
        sa.Column("external_reference", sa.String(100), nullable=True),
    )
    op.add_column(
        "trips",
        sa.Column("pricing_rules_json", JSONB, nullable=True),
        # Example: {"partner1": {"markup_pct": 5}, "default": {"markup_pct": 0}}
    )

    # Source tracking (for imported circuits)
    op.add_column(
        "trips",
        sa.Column("source_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "trips",
        sa.Column("source_imported_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Index for distribution queries
    op.create_index("ix_trips_is_distributable", "trips", ["is_distributable"])
    op.create_index("ix_trips_external_reference", "trips", ["external_reference"])


def downgrade() -> None:
    op.drop_index("ix_trips_external_reference", table_name="trips")
    op.drop_index("ix_trips_is_distributable", table_name="trips")

    op.drop_column("trips", "source_imported_at")
    op.drop_column("trips", "source_url")
    op.drop_column("trips", "pricing_rules_json")
    op.drop_column("trips", "external_reference")
    op.drop_column("trips", "distribution_channels")
    op.drop_column("trips", "is_distributable")
