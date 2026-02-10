"""Add notes and ai_warnings fields to contracts table.

Revision ID: 030_contract_notes
Revises: 029_season_original_name
Create Date: 2025-02-07

Adds:
- notes: Manual notes for the contract
- ai_warnings: JSON array of warnings extracted by AI from PDF
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "030_contract_notes"
down_revision = "029_season_original_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add notes column for manual notes
    op.add_column(
        'contracts',
        sa.Column('notes', sa.String(2000), nullable=True)
    )

    # Add ai_warnings column for AI-extracted warnings (JSON array)
    op.add_column(
        'contracts',
        sa.Column('ai_warnings', sa.JSON(), nullable=True, server_default='[]')
    )


def downgrade() -> None:
    op.drop_column('contracts', 'ai_warnings')
    op.drop_column('contracts', 'notes')
