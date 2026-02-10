"""Add accommodation_photos table

Revision ID: 031_accommodation_photos
Revises: 030_contract_notes
Create Date: 2025-02-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "031_accommodation_photos"
down_revision = "030_contract_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accommodation_photos",
        # Primary key
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),

        # Foreign keys
        sa.Column("accommodation_id", sa.BigInteger(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=True),  # NULL = hotel-level photo

        # Storage paths
        sa.Column("storage_path", sa.String(500), nullable=False),  # photos/tenant/acc_123/uuid.jpg
        sa.Column("url", sa.String(1000), nullable=False),  # Public URL (original)
        sa.Column("thumbnail_url", sa.String(1000), nullable=True),  # 150px thumbnail

        # Optimized variants (Phase 2)
        sa.Column("url_avif", sa.String(1000), nullable=True),
        sa.Column("url_webp", sa.String(1000), nullable=True),
        sa.Column("url_medium", sa.String(1000), nullable=True),  # 800px
        sa.Column("url_large", sa.String(1000), nullable=True),   # 1920px
        sa.Column("srcset_json", sa.Text(), nullable=True),  # JSON with all responsive URLs
        sa.Column("lqip_data_url", sa.Text(), nullable=True),  # Base64 blur placeholder (20px)

        # Metadata
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),  # Bytes
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("caption", sa.String(500), nullable=True),
        sa.Column("alt_text", sa.String(255), nullable=True),

        # Flags
        sa.Column("is_main", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_processed", sa.Boolean(), server_default="false", nullable=False),  # True when variants generated
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accommodation_id"], ["accommodations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_category_id"], ["room_categories.id"], ondelete="SET NULL"),
    )

    # Indexes for common queries
    op.create_index("ix_accommodation_photos_tenant", "accommodation_photos", ["tenant_id"])
    op.create_index("ix_accommodation_photos_accommodation", "accommodation_photos", ["accommodation_id"])
    op.create_index("ix_accommodation_photos_room_category", "accommodation_photos", ["room_category_id"])
    op.create_index("ix_accommodation_photos_is_main", "accommodation_photos", ["accommodation_id", "is_main"])
    op.create_index("ix_accommodation_photos_sort_order", "accommodation_photos", ["accommodation_id", "room_category_id", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_accommodation_photos_sort_order", table_name="accommodation_photos")
    op.drop_index("ix_accommodation_photos_is_main", table_name="accommodation_photos")
    op.drop_index("ix_accommodation_photos_room_category", table_name="accommodation_photos")
    op.drop_index("ix_accommodation_photos_accommodation", table_name="accommodation_photos")
    op.drop_index("ix_accommodation_photos_tenant", table_name="accommodation_photos")
    op.drop_table("accommodation_photos")
