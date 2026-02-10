"""
PaymentTerms model - Payment conditions for suppliers.
Supports multiple installments with different due dates.
"""

from typing import Optional, List, TYPE_CHECKING
from enum import Enum

from sqlalchemy import String, Boolean, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.supplier import Supplier


class PaymentDueDateReference(str, Enum):
    """Reference point for payment due date calculation."""
    CONFIRMATION = "confirmation"  # At booking confirmation
    DEPARTURE = "departure"        # Relative to departure date
    SERVICE = "service"            # Relative to service date
    RETURN = "return"              # Relative to return date
    INVOICE = "invoice"            # Relative to invoice date


class PaymentTerms(TenantBase):
    """
    Payment terms/conditions for a supplier.
    Defines installment schedule (e.g., 30% at confirmation, 70% 14 days before departure).

    Installments are stored as JSONB array:
    [
        {"percentage": 30, "reference": "confirmation", "days_offset": 0, "label": "Acompte"},
        {"percentage": 70, "reference": "departure", "days_offset": -14, "label": "Solde"}
    ]
    """

    __tablename__ = "payment_terms"

    # Supplier this belongs to (optional - can be global template)
    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Standard 30/70"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Installments (JSONB array)
    # Each installment: {percentage, reference, days_offset, label}
    installments: Mapped[List[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # Status
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # Default for this supplier
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="raise")
    supplier: Mapped[Optional["Supplier"]] = relationship(
        "Supplier",
        foreign_keys=[supplier_id],
        lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<PaymentTerms(id={self.id}, name='{self.name}', supplier_id={self.supplier_id})>"
