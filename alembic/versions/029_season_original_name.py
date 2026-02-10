"""Add original_name to accommodation_seasons for contract harmonization.

Revision ID: 029_season_original_name
Revises: 028_contract_rates_table
Create Date: 2025-02-07

Adds original_name field to store the original season name from contracts
before harmonization to standard nomenclature (HS, BS, MS, PEAK).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "029_season_original_name"
down_revision = "028_contract_rates_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add original_name column
    op.add_column(
        'accommodation_seasons',
        sa.Column('original_name', sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('accommodation_seasons', 'original_name')
