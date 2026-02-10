"""Add accommodation_extras table for optional supplements.

Revision ID: 025_accommodation_extras
Revises: 024_season_year_string
Create Date: 2025-02-07

Adds a table for optional extras/supplements like breakfast, transfers, etc.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "025_accommodation_extras"
down_revision = "024_season_year_string"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'accommodation_extras',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('accommodation_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(20), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('extra_type', sa.String(30), nullable=False, server_default='meal'),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
        sa.Column('pricing_model', sa.String(30), nullable=False, server_default='per_person_per_night'),
        sa.Column('season_id', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('is_included', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_mandatory', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['accommodation_id'], ['accommodations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['accommodation_seasons.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_accommodation_extras_accommodation_id', 'accommodation_extras', ['accommodation_id'])


def downgrade() -> None:
    op.drop_index('ix_accommodation_extras_accommodation_id', table_name='accommodation_extras')
    op.drop_table('accommodation_extras')
