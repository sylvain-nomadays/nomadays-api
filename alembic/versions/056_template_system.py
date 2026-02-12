"""Add template system columns for formula and day templates.

Adds versioning, categorization, and metadata columns to support
the template system with synchronization.

Revision ID: 056_template_system
Revises: 055_roadbook_fields
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "056_template_system"
down_revision = "055_roadbook_fields"


def upgrade() -> None:
    # ── Formulas: template versioning & metadata ──────────────────────────
    op.add_column("formulas", sa.Column(
        "template_version", sa.Integer(), nullable=False, server_default="1",
    ))
    op.add_column("formulas", sa.Column(
        "template_source_version", sa.Integer(), nullable=True,
    ))
    op.add_column("formulas", sa.Column(
        "template_category", sa.String(20), nullable=True,
    ))
    op.add_column("formulas", sa.Column(
        "template_tags", JSONB(), nullable=True,
    ))
    op.add_column("formulas", sa.Column(
        "template_location_id", sa.BigInteger(), nullable=True,
    ))
    op.add_column("formulas", sa.Column(
        "template_country_code", sa.String(2), nullable=True,
    ))

    # FK for template_location_id → locations.id
    op.create_foreign_key(
        "fk_formulas_template_location",
        "formulas", "locations",
        ["template_location_id"], ["id"],
        ondelete="SET NULL",
    )

    # Index for fast template listing
    op.create_index(
        "idx_formulas_tenant_is_template",
        "formulas",
        ["tenant_id", "is_template"],
    )

    # ── TripDays: template metadata ───────────────────────────────────────
    op.add_column("trip_days", sa.Column(
        "is_template", sa.Boolean(), nullable=False, server_default="false",
    ))
    op.add_column("trip_days", sa.Column(
        "template_version", sa.Integer(), nullable=False, server_default="1",
    ))
    op.add_column("trip_days", sa.Column(
        "template_tags", JSONB(), nullable=True,
    ))


def downgrade() -> None:
    # TripDays
    op.drop_column("trip_days", "template_tags")
    op.drop_column("trip_days", "template_version")
    op.drop_column("trip_days", "is_template")

    # Formulas
    op.drop_index("idx_formulas_tenant_is_template", table_name="formulas")
    op.drop_constraint("fk_formulas_template_location", "formulas", type_="foreignkey")
    op.drop_column("formulas", "template_country_code")
    op.drop_column("formulas", "template_location_id")
    op.drop_column("formulas", "template_tags")
    op.drop_column("formulas", "template_category")
    op.drop_column("formulas", "template_source_version")
    op.drop_column("formulas", "template_version")
