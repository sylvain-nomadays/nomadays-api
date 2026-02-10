"""Add content article system tables

Creates tables for multi-language SEO content:
- content_entities: Main entities (attractions, destinations, activities, etc.)
- content_translations: Per-language content (title, slug, markdown, SEO)
- content_photos: Photos with optimized variants
- content_tags: Hierarchical tags with translations
- content_entity_tags: Junction table for many-to-many
- content_relations: Links between entities

Revision ID: 032_content_articles
Revises: 031_accommodation_photos
Create Date: 2025-02-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "032_content_articles"
down_revision = "031_accommodation_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # Table: content_entities
    # =========================================================================
    op.create_table(
        "content_entities",
        # Primary key as UUID
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Tenant isolation
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),

        # Type and status
        sa.Column("entity_type", sa.String(20), nullable=False),  # attraction, destination, activity, etc.
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),  # draft, review, published, archived

        # Geographic location
        sa.Column("location_id", sa.BigInteger(), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("google_place_id", sa.String(255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),

        # Hierarchy (Region > Destination > Attractions)
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),

        # Linked entities (cross-system references)
        sa.Column("supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("accommodation_id", sa.BigInteger(), nullable=True),

        # Rating and quality
        sa.Column("rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("rating_count", sa.Integer(), server_default="0"),
        sa.Column("internal_priority", sa.Integer(), server_default="0"),

        # SEO metadata
        sa.Column("canonical_url", sa.String(500), nullable=True),
        sa.Column("meta_robots", sa.String(50), server_default="index,follow"),
        sa.Column("structured_data_json", JSONB, nullable=True),

        # Cover image
        sa.Column("cover_image_url", sa.String(1000), nullable=True),
        sa.Column("cover_image_alt", sa.String(255), nullable=True),

        # AI generation tracking
        sa.Column("ai_generation_status", sa.String(20), nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_model_used", sa.String(50), nullable=True),
        sa.Column("ai_prompt_used", sa.Text(), nullable=True),

        # Flags
        sa.Column("is_featured", sa.Boolean(), server_default="false"),
        sa.Column("view_count", sa.Integer(), server_default="0"),

        # Audit
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Foreign keys
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["content_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accommodation_id"], ["accommodations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Indexes for content_entities
    op.create_index("ix_content_entities_tenant_id", "content_entities", ["tenant_id"])
    op.create_index("ix_content_entities_entity_type", "content_entities", ["entity_type"])
    op.create_index("ix_content_entities_status", "content_entities", ["status"])
    op.create_index("ix_content_entities_parent_id", "content_entities", ["parent_id"])
    op.create_index("ix_content_entities_location_id", "content_entities", ["location_id"])
    op.create_index("ix_content_entities_supplier_id", "content_entities", ["supplier_id"])
    op.create_index("ix_content_entities_accommodation_id", "content_entities", ["accommodation_id"])
    op.create_index("ix_content_entities_is_featured", "content_entities", ["is_featured"])
    op.create_index("ix_content_entities_tenant_type", "content_entities", ["tenant_id", "entity_type"])
    op.create_index("ix_content_entities_tenant_status", "content_entities", ["tenant_id", "status"])
    op.create_index("ix_content_entities_tenant_featured", "content_entities", ["tenant_id", "is_featured"])

    # =========================================================================
    # Table: content_translations
    # =========================================================================
    op.create_table(
        "content_translations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),

        # Language (2-letter ISO code)
        sa.Column("language_code", sa.String(2), nullable=False),

        # SEO-critical fields
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("meta_title", sa.String(70), nullable=True),  # 60-70 chars
        sa.Column("meta_description", sa.String(170), nullable=True),  # 160 chars

        # Content
        sa.Column("excerpt", sa.String(500), nullable=True),  # 150-200 chars
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=True),  # Cached render

        # AI tracking per translation
        sa.Column("ai_generation_status", sa.String(20), nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("ai_reviewed_at", sa.DateTime(timezone=True), nullable=True),

        # Flags
        sa.Column("is_primary", sa.Boolean(), server_default="false"),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("reading_time_minutes", sa.Integer(), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Foreign keys and constraints
        sa.ForeignKeyConstraint(["entity_id"], ["content_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("entity_id", "language_code", name="uq_content_translation_entity_lang"),
    )

    # Indexes for content_translations
    op.create_index("ix_content_translations_entity_id", "content_translations", ["entity_id"])
    op.create_index("ix_content_translations_language_code", "content_translations", ["language_code"])
    op.create_index("ix_content_translations_slug", "content_translations", ["slug"])

    # =========================================================================
    # Table: content_photos
    # =========================================================================
    op.create_table(
        "content_photos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),

        # Storage and URLs
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("thumbnail_url", sa.String(1000), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),

        # Optimized variants
        sa.Column("url_avif", sa.String(1000), nullable=True),
        sa.Column("url_webp", sa.String(1000), nullable=True),
        sa.Column("url_medium", sa.String(1000), nullable=True),  # 800px
        sa.Column("url_large", sa.String(1000), nullable=True),   # 1920px
        sa.Column("srcset_json", JSONB, nullable=True),
        sa.Column("lqip_data_url", sa.Text(), nullable=True),  # Base64 blur

        # Metadata
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),

        # Multi-language caption and alt text
        sa.Column("caption_json", JSONB, nullable=True),  # {"fr": "...", "en": "..."}
        sa.Column("alt_text_json", JSONB, nullable=True),

        # Flags
        sa.Column("is_cover", sa.Boolean(), server_default="false"),
        sa.Column("is_processed", sa.Boolean(), server_default="false"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Foreign keys
        sa.ForeignKeyConstraint(["entity_id"], ["content_entities.id"], ondelete="CASCADE"),
    )

    # Indexes for content_photos
    op.create_index("ix_content_photos_entity_id", "content_photos", ["entity_id"])
    op.create_index("ix_content_photos_entity_cover", "content_photos", ["entity_id", "is_cover"])

    # =========================================================================
    # Table: content_tags
    # =========================================================================
    op.create_table(
        "content_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),

        # Tag identification
        sa.Column("slug", sa.String(100), nullable=False),

        # Hierarchy
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),

        # Multi-language labels
        sa.Column("labels_json", JSONB, nullable=False),  # {"fr": "Temples", "en": "Temples"}
        sa.Column("descriptions_json", JSONB, nullable=True),

        # Display
        sa.Column("color", sa.String(20), nullable=True),  # Hex color
        sa.Column("icon", sa.String(50), nullable=True),   # Icon name

        # Ordering
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Foreign keys and constraints
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["content_tags.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_content_tag_tenant_slug"),
    )

    # Indexes for content_tags
    op.create_index("ix_content_tags_tenant_id", "content_tags", ["tenant_id"])
    op.create_index("ix_content_tags_parent_id", "content_tags", ["parent_id"])
    op.create_index("ix_content_tags_slug", "content_tags", ["slug"])

    # =========================================================================
    # Table: content_entity_tags (Junction table)
    # =========================================================================
    op.create_table(
        "content_entity_tags",
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Primary key
        sa.PrimaryKeyConstraint("entity_id", "tag_id"),

        # Foreign keys
        sa.ForeignKeyConstraint(["entity_id"], ["content_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["content_tags.id"], ondelete="CASCADE"),
    )

    # Indexes for content_entity_tags
    op.create_index("ix_content_entity_tags_entity_id", "content_entity_tags", ["entity_id"])
    op.create_index("ix_content_entity_tags_tag_id", "content_entity_tags", ["tag_id"])

    # =========================================================================
    # Table: content_relations
    # =========================================================================
    op.create_table(
        "content_relations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),

        # Source and target
        sa.Column("source_entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", UUID(as_uuid=True), nullable=False),

        # Relation type
        sa.Column("relation_type", sa.String(20), nullable=False),  # part_of, near, related, see_also, includes

        # Ordering
        sa.Column("sort_order", sa.Integer(), server_default="0"),

        # Bidirectional?
        sa.Column("is_bidirectional", sa.Boolean(), server_default="false"),

        # Audit
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),

        # Foreign keys and constraints
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_entity_id"], ["content_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_entity_id"], ["content_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_entity_id", "target_entity_id", "relation_type", name="uq_content_relation_source_target_type"),
        sa.CheckConstraint("source_entity_id != target_entity_id", name="ck_content_relation_no_self_ref"),
    )

    # Indexes for content_relations
    op.create_index("ix_content_relations_tenant_id", "content_relations", ["tenant_id"])
    op.create_index("ix_content_relations_source_entity_id", "content_relations", ["source_entity_id"])
    op.create_index("ix_content_relations_target_entity_id", "content_relations", ["target_entity_id"])


def downgrade() -> None:
    # Drop tables in reverse order (respect foreign keys)
    op.drop_index("ix_content_relations_target_entity_id", table_name="content_relations")
    op.drop_index("ix_content_relations_source_entity_id", table_name="content_relations")
    op.drop_index("ix_content_relations_tenant_id", table_name="content_relations")
    op.drop_table("content_relations")

    op.drop_index("ix_content_entity_tags_tag_id", table_name="content_entity_tags")
    op.drop_index("ix_content_entity_tags_entity_id", table_name="content_entity_tags")
    op.drop_table("content_entity_tags")

    op.drop_index("ix_content_tags_slug", table_name="content_tags")
    op.drop_index("ix_content_tags_parent_id", table_name="content_tags")
    op.drop_index("ix_content_tags_tenant_id", table_name="content_tags")
    op.drop_table("content_tags")

    op.drop_index("ix_content_photos_entity_cover", table_name="content_photos")
    op.drop_index("ix_content_photos_entity_id", table_name="content_photos")
    op.drop_table("content_photos")

    op.drop_index("ix_content_translations_slug", table_name="content_translations")
    op.drop_index("ix_content_translations_language_code", table_name="content_translations")
    op.drop_index("ix_content_translations_entity_id", table_name="content_translations")
    op.drop_table("content_translations")

    op.drop_index("ix_content_entities_tenant_featured", table_name="content_entities")
    op.drop_index("ix_content_entities_tenant_status", table_name="content_entities")
    op.drop_index("ix_content_entities_tenant_type", table_name="content_entities")
    op.drop_index("ix_content_entities_is_featured", table_name="content_entities")
    op.drop_index("ix_content_entities_accommodation_id", table_name="content_entities")
    op.drop_index("ix_content_entities_supplier_id", table_name="content_entities")
    op.drop_index("ix_content_entities_location_id", table_name="content_entities")
    op.drop_index("ix_content_entities_parent_id", table_name="content_entities")
    op.drop_index("ix_content_entities_status", table_name="content_entities")
    op.drop_index("ix_content_entities_entity_type", table_name="content_entities")
    op.drop_index("ix_content_entities_tenant_id", table_name="content_entities")
    op.drop_table("content_entities")
