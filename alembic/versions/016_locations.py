"""Add locations table, supplier reservation contact, and accommodation location_id.

Revision ID: 016_locations
Revises: 015_excluded_seasons
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '016_locations'
down_revision: Union[str, None] = '015_excluded_seasons'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create locations table
    op.create_table(
        'locations',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=True),
        sa.Column('location_type', sa.String(50), nullable=False, server_default='city'),
        sa.Column('parent_id', sa.BigInteger(), nullable=True),
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('lat', sa.Numeric(10, 7), nullable=True),
        sa.Column('lng', sa.Numeric(10, 7), nullable=True),
        sa.Column('google_place_id', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content_id', sa.BigInteger(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['locations.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_locations_tenant_id', 'locations', ['tenant_id'])
    op.create_index('ix_locations_slug', 'locations', ['slug'])
    op.create_index('ix_locations_country_code', 'locations', ['country_code'])

    # 2. Add reservation contact fields to suppliers
    op.add_column('suppliers', sa.Column('reservation_email', sa.String(255), nullable=True))
    op.add_column('suppliers', sa.Column('reservation_phone', sa.String(100), nullable=True))

    # 3. Add location_id and content_id to accommodations
    op.add_column('accommodations', sa.Column('location_id', sa.Integer(), nullable=True))
    op.add_column('accommodations', sa.Column('content_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_accommodations_location_id',
        'accommodations', 'locations',
        ['location_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # 3. Remove location_id and content_id from accommodations
    op.drop_constraint('fk_accommodations_location_id', 'accommodations', type_='foreignkey')
    op.drop_column('accommodations', 'content_id')
    op.drop_column('accommodations', 'location_id')

    # 2. Remove reservation contact fields from suppliers
    op.drop_column('suppliers', 'reservation_phone')
    op.drop_column('suppliers', 'reservation_email')

    # 1. Drop locations table
    op.drop_index('ix_locations_country_code', 'locations')
    op.drop_index('ix_locations_slug', 'locations')
    op.drop_index('ix_locations_tenant_id', 'locations')
    op.drop_table('locations')
