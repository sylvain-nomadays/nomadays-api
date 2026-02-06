"""
Supplier model - hotels, activities, transport providers, etc.
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.contract import Contract


class Supplier(TenantBase):
    """
    A supplier providing services (hotels, activities, transport, etc.).
    """

    __tablename__ = "suppliers"

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String(50),  # Flexible string: accommodation, activity, transport, restaurant, guide, other
        nullable=False,
    )

    # Contact
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Location
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Financials
    tax_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="suppliers")
    contracts: Mapped[List["Contract"]] = relationship("Contract", back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name='{self.name}', type='{self.type}')>"
