"""
Supplier model - hotels, activities, transport providers, etc.
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, Integer, ForeignKey, ARRAY, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.contract import Contract
    from app.models.accommodation import Accommodation
    from app.models.payment_terms import PaymentTerms
    from app.models.location import Location


class Supplier(TenantBase):
    """
    A supplier providing services (hotels, activities, transport, etc.).
    Can have multiple types: accommodation + activity for example.
    """

    __tablename__ = "suppliers"

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Types: array of strings ['accommodation', 'activity', 'transport', 'restaurant', 'guide', 'other']
    # A supplier can provide multiple services
    types: Mapped[List[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        default=["accommodation"],
    )

    # Contact (commercial)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Contact reservation (default for all products, can be overridden per product)
    reservation_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reservation_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Location
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(nullable=True)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Link to Location entity for advanced filtering
    location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Web
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Financials
    tax_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_vat_registered: Mapped[bool] = mapped_column(Boolean, default=False)  # Assujetti TVA = TVA récupérable
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Legacy text field
    default_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)

    # Default payment terms (link to payment_terms table)
    default_payment_terms_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payment_terms.id", ondelete="SET NULL"), nullable=True
    )

    # Billing entity info (for logistics to know who to invoice)
    # If different from supplier name, use billing_entity_name
    billing_entity_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_entity_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Contract workflow status (user-managed workflow state)
    # - needs_contract: Default, needs a contract to be requested
    # - contract_requested: Logistics has requested contract from supplier
    # - dynamic_pricing: No contract needed, supplier uses dynamic pricing only
    contract_workflow_status: Mapped[str] = mapped_column(
        String(30), default="needs_contract", nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="suppliers", lazy="raise")
    contracts: Mapped[List["Contract"]] = relationship("Contract", back_populates="supplier", lazy="raise")
    accommodations: Mapped[List["Accommodation"]] = relationship(
        "Accommodation", back_populates="supplier", lazy="raise"
    )
    default_payment_terms: Mapped[Optional["PaymentTerms"]] = relationship(
        "PaymentTerms", foreign_keys=[default_payment_terms_id], lazy="raise"
    )
    location: Mapped[Optional["Location"]] = relationship("Location", lazy="raise")

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name='{self.name}', types={self.types})>"
