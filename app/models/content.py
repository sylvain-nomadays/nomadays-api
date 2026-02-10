"""
Content Article models for multi-language SEO content.

Supports:
- ContentEntity: Main entity (attraction, destination, activity, accommodation, eating, region)
- ContentTranslation: Per-language content (title, slug, markdown, SEO fields)
- ContentPhoto: Photos with optimized variants
- ContentTag: Hierarchical tags with translations
- ContentRelation: Links between entities (near, part_of, related, etc.)
"""

import uuid
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import (
    String, Boolean, Integer, ForeignKey, Text, BigInteger,
    DateTime, Numeric, Index, UniqueConstraint, CheckConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.location import Location
    from app.models.supplier import Supplier
    from app.models.accommodation import Accommodation


# ============================================================================
# Enums
# ============================================================================

import enum


class ContentEntityType(str, enum.Enum):
    """Types of content entities."""
    ATTRACTION = "attraction"
    DESTINATION = "destination"
    ACTIVITY = "activity"
    ACCOMMODATION = "accommodation"
    EATING = "eating"
    REGION = "region"


class ContentStatus(str, enum.Enum):
    """Publication status of content."""
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentRelationType(str, enum.Enum):
    """Types of relations between content entities."""
    PART_OF = "part_of"       # Attraction is part_of Destination
    NEAR = "near"             # Close proximity
    RELATED = "related"       # General relation
    SEE_ALSO = "see_also"     # Cross-reference
    INCLUDES = "includes"     # Region includes Destinations


class AIGenerationStatus(str, enum.Enum):
    """Status of AI content generation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEWED = "reviewed"


# ============================================================================
# ContentEntity - Main Entity
# ============================================================================

class ContentEntity(Base, TimestampMixin):
    """
    Main content entity representing an attraction, destination, activity, etc.

    Multi-tenant with UUID primary key for better distribution.
    Content is stored in ContentTranslation for multi-language support.
    """

    __tablename__ = "content_entities"

    # Primary key as UUID for better distribution
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Tenant isolation
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Type and status
    entity_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=ContentStatus.DRAFT.value,
        nullable=False,
        index=True,
    )

    # Geographic location
    location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Hierarchy (Region > Destination > Attractions)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Linked entities (cross-system references)
    supplier_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    accommodation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("accommodations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Rating and quality
    rating: Mapped[Optional[float]] = mapped_column(Numeric(2, 1), nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    internal_priority: Mapped[int] = mapped_column(Integer, default=0)

    # SEO metadata
    canonical_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    meta_robots: Mapped[str] = mapped_column(String(50), default="index,follow")
    structured_data_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Cover image
    cover_image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    cover_image_alt: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI generation tracking
    ai_generation_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_model_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ai_prompt_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Flags
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="raise")
    location: Mapped[Optional["Location"]] = relationship("Location", lazy="raise")
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", lazy="raise")
    accommodation: Mapped[Optional["Accommodation"]] = relationship("Accommodation", lazy="raise")
    parent: Mapped[Optional["ContentEntity"]] = relationship(
        "ContentEntity",
        remote_side=[id],
        lazy="raise",
        foreign_keys=[parent_id],
    )
    children: Mapped[List["ContentEntity"]] = relationship(
        "ContentEntity",
        back_populates="parent",
        lazy="raise",
        foreign_keys=[parent_id],
    )
    translations: Mapped[List["ContentTranslation"]] = relationship(
        "ContentTranslation",
        back_populates="entity",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    photos: Mapped[List["ContentPhoto"]] = relationship(
        "ContentPhoto",
        back_populates="entity",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    tags: Mapped[List["ContentTag"]] = relationship(
        "ContentTag",
        secondary="content_entity_tags",
        lazy="raise",
    )
    relations_from: Mapped[List["ContentRelation"]] = relationship(
        "ContentRelation",
        foreign_keys="ContentRelation.source_entity_id",
        back_populates="source_entity",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    relations_to: Mapped[List["ContentRelation"]] = relationship(
        "ContentRelation",
        foreign_keys="ContentRelation.target_entity_id",
        back_populates="target_entity",
        lazy="raise",
    )
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="raise",
    )
    updated_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by],
        lazy="raise",
    )

    __table_args__ = (
        Index("ix_content_entities_tenant_type", "tenant_id", "entity_type"),
        Index("ix_content_entities_tenant_status", "tenant_id", "status"),
        Index("ix_content_entities_tenant_featured", "tenant_id", "is_featured"),
    )

    def __repr__(self) -> str:
        return f"<ContentEntity(id={self.id}, type={self.entity_type}, status={self.status})>"


# ============================================================================
# ContentTranslation - Per-Language Content
# ============================================================================

class ContentTranslation(Base, TimestampMixin):
    """
    Translation of content entity in a specific language.

    Each entity can have multiple translations (FR, EN, IT, ES, DE).
    The is_primary flag indicates the main language for the entity.
    """

    __tablename__ = "content_translations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Language (2-letter ISO code)
    language_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # SEO-critical fields
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    meta_title: Mapped[Optional[str]] = mapped_column(String(70), nullable=True)  # 60-70 chars
    meta_description: Mapped[Optional[str]] = mapped_column(String(170), nullable=True)  # 160 chars

    # Content
    excerpt: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 150-200 chars
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Cached render

    # AI tracking per translation
    ai_generation_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ai_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Flags
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reading_time_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    entity: Mapped["ContentEntity"] = relationship(
        "ContentEntity",
        back_populates="translations",
        lazy="raise",
    )
    ai_reviewer: Mapped[Optional["User"]] = relationship("User", lazy="raise")

    __table_args__ = (
        UniqueConstraint("entity_id", "language_code", name="uq_content_translation_entity_lang"),
        Index("ix_content_translations_slug", "slug"),
    )

    def __repr__(self) -> str:
        return f"<ContentTranslation(id={self.id}, lang={self.language_code}, title={self.title[:30]}...)>"


# ============================================================================
# ContentPhoto - Photos with Optimized Variants
# ============================================================================

class ContentPhoto(Base, TimestampMixin):
    """
    Photo associated with a content entity.

    Follows the same pattern as AccommodationPhoto for consistency.
    Supports multi-language captions via JSONB.
    """

    __tablename__ = "content_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Storage and URLs
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Optimized variants (populated by image processing worker)
    url_avif: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url_webp: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url_medium: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # 800px
    url_large: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)   # 1920px
    srcset_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    lqip_data_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Base64 blur

    # Metadata
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Multi-language caption and alt text
    caption_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # {"fr": "...", "en": "..."}
    alt_text_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Flags
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    entity: Mapped["ContentEntity"] = relationship(
        "ContentEntity",
        back_populates="photos",
        lazy="raise",
    )

    __table_args__ = (
        Index("ix_content_photos_entity_cover", "entity_id", "is_cover"),
    )

    def __repr__(self) -> str:
        return f"<ContentPhoto(id={self.id}, entity_id={self.entity_id}, is_cover={self.is_cover})>"


# ============================================================================
# ContentTag - Hierarchical Tags with Translations
# ============================================================================

class ContentTag(Base, TimestampMixin):
    """
    Tag for categorizing content entities.

    Supports hierarchy (parent_id) and multi-language labels via JSONB.
    """

    __tablename__ = "content_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tag identification
    slug: Mapped[str] = mapped_column(String(100), nullable=False)

    # Hierarchy
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_tags.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Multi-language labels
    labels_json: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"fr": "Temples", "en": "Temples"}
    descriptions_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Display
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Hex color
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)   # Icon name

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    parent: Mapped[Optional["ContentTag"]] = relationship(
        "ContentTag",
        remote_side=[id],
        lazy="raise",
    )
    children: Mapped[List["ContentTag"]] = relationship(
        "ContentTag",
        back_populates="parent",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_content_tag_tenant_slug"),
    )

    def __repr__(self) -> str:
        return f"<ContentTag(id={self.id}, slug={self.slug})>"


# ============================================================================
# ContentEntityTag - Junction Table
# ============================================================================

from sqlalchemy import Table, Column

content_entity_tags = Table(
    "content_entity_tags",
    Base.metadata,
    Column(
        "entity_id",
        UUID(as_uuid=True),
        ForeignKey("content_entities.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("content_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
    ),
)


# ============================================================================
# ContentRelation - Links Between Entities
# ============================================================================

class ContentRelation(Base, TimestampMixin):
    """
    Relation between two content entities.

    Examples:
    - Attraction is part_of Destination
    - Attraction is near another Attraction
    - Region includes multiple Destinations
    """

    __tablename__ = "content_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source and target
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relation type
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Bidirectional?
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, default=False)

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    source_entity: Mapped["ContentEntity"] = relationship(
        "ContentEntity",
        foreign_keys=[source_entity_id],
        back_populates="relations_from",
        lazy="raise",
    )
    target_entity: Mapped["ContentEntity"] = relationship(
        "ContentEntity",
        foreign_keys=[target_entity_id],
        back_populates="relations_to",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id", "target_entity_id", "relation_type",
            name="uq_content_relation_source_target_type"
        ),
        CheckConstraint(
            "source_entity_id != target_entity_id",
            name="ck_content_relation_no_self_ref"
        ),
        Index("ix_content_relations_target", "target_entity_id"),
    )

    def __repr__(self) -> str:
        return f"<ContentRelation(id={self.id}, type={self.relation_type})>"


# ============================================================================
# ContentCTABlock - Call-To-Action Blocks
# ============================================================================

class CTAType(str, enum.Enum):
    """Types of CTA blocks."""
    QUOTE_REQUEST = "quote_request"  # Demande de devis
    RELATED_CIRCUIT = "related_circuit"  # Suggestion de circuit


class CTAPosition(str, enum.Enum):
    """Position where CTA can be inserted."""
    AFTER_INTRO = "after_intro"  # After ~300 words
    MIDDLE = "middle"  # Middle of content
    AFTER_CONTENT = "after_content"  # End of main content
    SIDEBAR = "sidebar"  # Sticky in sidebar


class ContentCTABlock(Base, TimestampMixin):
    """
    CTA block configuration for content pages.

    Two main types:
    - quote_request: "Demande de devis" - calls to action for custom trip quotes
    - related_circuit: "Suggestion circuit" - link to circuits passing through destination

    Supports multilingual content via JSONB fields.
    """

    __tablename__ = "content_cta_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # CTA Type
    cta_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Internal name for management
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Multilingual content (JSONB: {"fr": "...", "en": "..."})
    title_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    button_text_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Action configuration
    button_action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # link, modal, form
    button_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Targeting
    entity_types: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True
    )  # ['destination', 'attraction']
    insert_position: Mapped[str] = mapped_column(
        String(50), default="after_content"
    )

    # Styling
    style: Mapped[str] = mapped_column(String(50), default="card")  # card, banner, inline
    background_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # #FEF7ED
    text_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # sparkles, phone

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def get_title(self, language: str = "fr") -> str:
        """Get title for specified language with fallback."""
        if self.title_json:
            return self.title_json.get(language) or self.title_json.get("fr") or ""
        return ""

    def get_description(self, language: str = "fr") -> Optional[str]:
        """Get description for specified language with fallback."""
        if self.description_json:
            return self.description_json.get(language) or self.description_json.get("fr")
        return None

    def get_button_text(self, language: str = "fr") -> str:
        """Get button text for specified language with fallback."""
        if self.button_text_json:
            return self.button_text_json.get(language) or self.button_text_json.get("fr") or "En savoir plus"
        return "En savoir plus"

    def __repr__(self) -> str:
        return f"<ContentCTABlock(id={self.id}, type={self.cta_type}, name={self.name})>"
