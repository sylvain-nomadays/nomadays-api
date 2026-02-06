"""add_missing_trip_columns

Revision ID: 38da96d5dbad
Revises: 001_quotation
Create Date: 2026-02-06 13:11:26.462076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '38da96d5dbad'
down_revision: Union[str, None] = '001_quotation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to trips table
    op.add_column('trips', sa.Column('operator_commission_pct', sa.DECIMAL(5, 2), nullable=True, server_default='0.00'))
    op.add_column('trips', sa.Column('currency_rates_json', sa.JSON(), nullable=True))
    op.add_column('trips', sa.Column('created_by_id', UUID(as_uuid=True), nullable=True))
    op.add_column('trips', sa.Column('assigned_to_id', UUID(as_uuid=True), nullable=True))

    # Add foreign keys
    op.create_foreign_key('fk_trips_created_by', 'trips', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_trips_assigned_to', 'trips', 'users', ['assigned_to_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_trips_assigned_to', 'trips', type_='foreignkey')
    op.drop_constraint('fk_trips_created_by', 'trips', type_='foreignkey')
    op.drop_column('trips', 'assigned_to_id')
    op.drop_column('trips', 'created_by_id')
    op.drop_column('trips', 'currency_rates_json')
    op.drop_column('trips', 'operator_commission_pct')
