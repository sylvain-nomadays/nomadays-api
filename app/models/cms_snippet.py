"""
CMS Snippets — Lightweight key-value content store for editable UI texts.

Used by:
- Client space (FAQ, sidebar, welcome texts, fidelity tiers)
- Tenant-specific overrides (each DMC can customize their texts)
- Global defaults (super admin sets fallback content)

Resolution order: tenant-specific → global (tenant_id IS NULL) → hardcoded fallback
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CmsSnippet(Base, TimestampMixin):
    """
    A snippet is a lightweight content unit identified by a unique key.

    Examples:
      - snippet_key="faq.programme", category="faq"
      - snippet_key="sidebar.collectif.title", category="sidebar"
      - snippet_key="welcome.proverb", category="welcome"
      - snippet_key="fidelity.tier.1.label", category="fidelity"

    content_json stores multilingual content: {"fr": "...", "en": "..."}
    metadata_json stores extra structured data (icon, keywords, question text, etc.)
    """

    __tablename__ = "cms_snippets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Tenant scoping — NULL means global (managed by super admin)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Identity
    snippet_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Content (multilingual)
    content_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'",
    )

    # Extra metadata (icon, keywords, question text, thresholds, etc.)
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Status & ordering
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "snippet_key", name="uq_cms_snippets_tenant_key"),
        Index("idx_cms_snippets_tenant_category", "tenant_id", "category"),
        Index("idx_cms_snippets_key", "snippet_key"),
    )

    def __repr__(self) -> str:
        return f"<CmsSnippet key={self.snippet_key!r} tenant={self.tenant_id}>"
