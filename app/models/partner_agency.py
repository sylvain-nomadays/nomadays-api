"""
Partner Agency model - B2B partners for white-label documents.

Partner agencies can have:
- Custom branding (logo, colors)
- Custom templates (booking conditions, cancellation policy, etc.)
- PDF styling configuration
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.dossier import Dossier


class PartnerAgency(TenantBase):
    """
    A B2B partner agency.
    When a dossier is linked to a partner, documents are generated
    with the partner's branding and templates.
    """

    __tablename__ = "partner_agencies"

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Contact info
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Branding
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # #1a5f4a
    secondary_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    accent_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    font_family: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # PDF configuration
    pdf_header_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_footer_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_style: Mapped[str] = mapped_column(String(50), default="modern")  # modern, classic, minimal

    # Templates
    template_booking_conditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    template_cancellation_policy: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    template_general_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    template_legal_mentions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Additional settings
    settings_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    dossiers: Mapped[List["Dossier"]] = relationship(
        "Dossier",
        back_populates="partner_agency",
    )

    def __repr__(self) -> str:
        return f"<PartnerAgency(id={self.id}, name='{self.name}')>"

    def get_template(self, template_type: str) -> Optional[str]:
        """Get template content by type."""
        template_map = {
            "booking_conditions": self.template_booking_conditions,
            "cancellation_policy": self.template_cancellation_policy,
            "general_info": self.template_general_info,
            "legal_mentions": self.template_legal_mentions,
        }
        template = template_map.get(template_type)
        if template and isinstance(template, dict):
            return template.get("content", "")
        return None

    def get_branding(self) -> dict:
        """Get branding configuration for PDF generation."""
        return {
            "logo_url": self.logo_url,
            "primary_color": self.primary_color or "#1a5f4a",
            "secondary_color": self.secondary_color or "#f0f9f4",
            "accent_color": self.accent_color or "#10b981",
            "font_family": self.font_family or "Inter",
            "pdf_style": self.pdf_style,
            "pdf_header_html": self.pdf_header_html,
            "pdf_footer_html": self.pdf_footer_html,
        }
