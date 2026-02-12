"""Add 'option' and 'non_reactive' values to dossier_status_enum.

- option: Client hasn't paid yet but pre-bookings are launched / a trip is selected
- non_reactive: Client is not responding, needs follow-up

Revision ID: 063_dossier_new_statuses
Revises: 062_dossier_selection_fields
Create Date: 2026-02-12
"""
from alembic import op

revision = "063_dossier_new_statuses"
down_revision = "062_dossier_selection_fields"


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction
    op.execute("COMMIT")
    op.execute("ALTER TYPE dossier_status_enum ADD VALUE IF NOT EXISTS 'option' AFTER 'negotiation'")
    op.execute("ALTER TYPE dossier_status_enum ADD VALUE IF NOT EXISTS 'non_reactive' AFTER 'negotiation'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    pass
