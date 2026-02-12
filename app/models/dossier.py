"""
Dossier model - represents a client travel inquiry/project.
A Dossier can have multiple Trip proposals, only one gets confirmed.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, DateTime, DECIMAL, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.tenant import Tenant
    from app.models.trip import Trip
    from app.models.partner_agency import PartnerAgency
    from app.models.invoice import Invoice


# Dossier status enum
DOSSIER_STATUS_ENUM = SQLEnum(
    "lead",
    "quote_in_progress",
    "quote_sent",
    "negotiation",
    "non_reactive",
    "option",
    "confirmed",
    "deposit_paid",
    "fully_paid",
    "in_trip",
    "completed",
    "lost",
    "cancelled",
    "archived",
    name="dossier_status_enum"
)


class Dossier(Base, TimestampMixin):
    """
    A client travel inquiry/project.
    Can contain multiple Trip proposals for quotation.
    """

    __tablename__ = "dossiers"

    # Primary key as UUID (to match Supabase style)
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

    # Reference (auto-generated or manual)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        DOSSIER_STATUS_ENUM,
        default="lead",
        nullable=False,
    )

    # Client information
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    client_company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Travel dates
    departure_date_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    departure_date_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Budget
    budget_min: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    budget_max: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    budget_currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Number of travelers
    pax_adults: Mapped[int] = mapped_column(default=2)
    pax_children: Mapped[int] = mapped_column(default=0)
    pax_infants: Mapped[int] = mapped_column(default=0)

    # Destination
    destination_countries: Mapped[Optional[list]] = mapped_column(
        ARRAY(String(2)),
        nullable=True,
    )

    # Marketing source
    marketing_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    marketing_campaign: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Internal notes
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lost/cancelled reason
    lost_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lost_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Priority / Hot lead
    is_hot: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(default=0)  # 0=normal, 1=high, 2=urgent

    # Ownership
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Trip selection (set when a trip proposal is confirmed)
    selected_trip_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    selected_cotation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    selected_cotation_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    final_pax_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    status_before_selection: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    selected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Last activity tracking
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Partner agency (B2B white-label)
    partner_agency_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("partner_agencies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="dossiers")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    assigned_to: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to_id])
    trips: Mapped[List["Trip"]] = relationship(
        "Trip",
        back_populates="dossier",
        cascade="all, delete-orphan",
        foreign_keys="[Trip.dossier_id]",
    )
    selected_trip: Mapped[Optional["Trip"]] = relationship(
        "Trip",
        foreign_keys=[selected_trip_id],
        uselist=False,
    )
    partner_agency: Mapped[Optional["PartnerAgency"]] = relationship(
        "PartnerAgency",
        back_populates="dossiers",
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="dossier",
    )

    def __repr__(self) -> str:
        return f"<Dossier(id={self.id}, reference='{self.reference}', status='{self.status}')>"

    @property
    def total_pax(self) -> int:
        """Total number of travelers."""
        return self.pax_adults + self.pax_children + self.pax_infants

    def can_confirm_trip(self) -> bool:
        """Check if a trip can be confirmed for this dossier."""
        return self.status not in ("cancelled", "lost", "archived")
