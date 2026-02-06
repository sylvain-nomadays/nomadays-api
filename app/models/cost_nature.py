"""
Cost Nature model - defines how an item cost is processed after confirmation.
Each nature triggers different downstream actions (booking, payroll, etc.).
"""

from typing import Optional

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class CostNature(TenantBase):
    """
    Nature of a cost item. Determines what happens after trip confirmation:
    - supplier: generates booking + payment schedule
    - salary: generates payroll assignment
    - allowance: generates cash advance
    - purchase: generates purchase order
    """

    __tablename__ = "cost_natures"

    # Identity
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    # What gets generated on confirmation
    generates_booking: Mapped[bool] = mapped_column(Boolean, default=False)
    generates_purchase_order: Mapped[bool] = mapped_column(Boolean, default=False)
    generates_payroll: Mapped[bool] = mapped_column(Boolean, default=False)
    generates_advance: Mapped[bool] = mapped_column(Boolean, default=False)

    # Accounting
    vat_recoverable_default: Mapped[bool] = mapped_column(Boolean, default=False)
    accounting_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # System flag (non-deletable)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<CostNature(id={self.id}, code='{self.code}', label='{self.label}')>"
