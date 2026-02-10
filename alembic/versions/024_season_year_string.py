"""Change year column from integer to string in accommodation_seasons.

Revision ID: 024_season_year_string
Revises: 023_supplier_billing_entity
Create Date: 2025-02-07

Allows storing year ranges like "2024-2025" instead of just integers.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "024_season_year_string"
down_revision = "023_supplier_billing_entity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert year column from INTEGER to VARCHAR(20)
    # First, we need to drop the old column and add a new one with the right type
    # PostgreSQL doesn't allow direct type change from INT to VARCHAR easily

    # Add temporary column
    op.add_column(
        'accommodation_seasons',
        sa.Column('year_str', sa.String(20), nullable=True)
    )

    # Copy data (converting int to string)
    op.execute("UPDATE accommodation_seasons SET year_str = year::TEXT WHERE year IS NOT NULL")

    # Drop old column
    op.drop_column('accommodation_seasons', 'year')

    # Rename new column
    op.alter_column('accommodation_seasons', 'year_str', new_column_name='year')


def downgrade() -> None:
    # Add temporary column
    op.add_column(
        'accommodation_seasons',
        sa.Column('year_int', sa.Integer(), nullable=True)
    )

    # Copy data (converting string to int where possible)
    op.execute("""
        UPDATE accommodation_seasons
        SET year_int = CAST(year AS INTEGER)
        WHERE year ~ '^[0-9]+$'
    """)

    # Drop old column
    op.drop_column('accommodation_seasons', 'year')

    # Rename new column
    op.alter_column('accommodation_seasons', 'year_int', new_column_name='year')
