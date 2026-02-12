"""Add location_photos table.

Revision ID: 050_location_photos
Revises: 049_trip_room_demand
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "050_location_photos"
down_revision = "049_trip_room_demand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_photos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "location_id",
            sa.BigInteger,
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Storage
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("thumbnail_url", sa.String(1000), nullable=True),
        sa.Column("url_avif", sa.String(1000), nullable=True),
        sa.Column("url_webp", sa.String(1000), nullable=True),
        sa.Column("url_medium", sa.String(1000), nullable=True),
        sa.Column("url_large", sa.String(1000), nullable=True),
        sa.Column("lqip_data_url", sa.Text, nullable=True),
        # Metadata
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("caption", sa.String(500), nullable=True),
        sa.Column("alt_text", sa.String(255), nullable=True),
        # Flags
        sa.Column("is_main", sa.Boolean, default=False),
        sa.Column("sort_order", sa.Integer, default=0),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
    )

    # Indexes
    op.create_index(
        "ix_location_photos_tenant",
        "location_photos",
        ["tenant_id"],
    )
    op.create_index(
        "ix_location_photos_location",
        "location_photos",
        ["location_id"],
    )
    op.create_index(
        "ix_location_photos_sort",
        "location_photos",
        ["location_id", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_location_photos_sort", table_name="location_photos")
    op.drop_index("ix_location_photos_location", table_name="location_photos")
    op.drop_index("ix_location_photos_tenant", table_name="location_photos")
    op.drop_table("location_photos")
