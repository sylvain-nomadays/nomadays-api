"""Add day_number_end to trip_days for multi-day support.

Revision ID: 035_trip_day_number_end
Revises: 034_trip_photos
Create Date: 2025-06-01
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '035_trip_day_number_end'
down_revision = '034_trip_photos'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('trip_days', sa.Column('day_number_end', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('trip_days', 'day_number_end')
