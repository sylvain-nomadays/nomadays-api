"""
TripInsurance model — Chapka Explorer integration (READY, not connected).
Tracks travel insurance quotes and policies per dossier.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, DateTime, Integer, DECIMAL, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.dossier import Dossier
    from app.models.invoice import Invoice


class TripInsurance(TenantBase):
    """
    Travel insurance record linked to a dossier.
    Chapka READY: models and CRUD exist, but no external API connection.

    Types: assistance, annulation, multirisques
    Commission: 25% Nomadays on premium
    """

    __tablename__ = "trip_insurances"

    # References
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Insurance type
    insurance_type: Mapped[str] = mapped_column(
        SQLEnum("assistance", "annulation", "multirisques", name="insurance_type_enum"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), server_default="chapka")
    policy_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Pricing
    premium_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    commission_pct: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), server_default="25.00")
    commission_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum("quoted", "active", "cancelled", name="insurance_status_enum"),
        server_default="quoted",
    )

    # Coverage period
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    pax_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    dossier: Mapped["Dossier"] = relationship("Dossier")
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice")

    def __repr__(self) -> str:
        return f"<TripInsurance(id={self.id}, type='{self.insurance_type}', status='{self.status}')>"


# Imports at end to avoid circular imports
from app.models.dossier import Dossier
from app.models.invoice import Invoice
