"""Add status_before_selection to dossiers.

Stores the dossier status before a trip was selected,
so we can restore it on deselection.

Revision ID: 064_status_before_select
Revises: 063_dossier_new_statuses
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = "064_status_before_select"
down_revision = "063_dossier_new_statuses"


def upgrade() -> None:
    op.add_column(
        "dossiers",
        sa.Column("status_before_selection", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dossiers", "status_before_selection")
