"""
Contract and ContractRate models - supplier agreements with pricing.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
import uuid

from sqlalchemy import BigInteger, String, Date, DateTime, Boolean, DECIMAL, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.supplier import Supplier
    from app.models.user import User


class Contract(TenantBase):
    """
    A contract with a supplier defining rates and terms.
    Contracts have validity periods and can be chained for renewals.
    """

    __tablename__ = "contracts"

    # Supplier relationship
    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # File storage
    file_storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Validity period
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)

    # Payment & cancellation terms (JSON for flexibility)
    payment_terms_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=lambda: {"deposit_pct": 20, "balance_days_before": 15}
    )
    cancellation_terms_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Notes and warnings extracted by AI
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)  # Manual notes
    ai_warnings: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True, default=list)  # AI-extracted warnings

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "draft",
            "active",
            "expiring_soon",
            "expired",
            "renewed",
            "archived",
            name="contract_status_enum"
        ),
        default="draft",
    )

    # AI extraction tracking
    ai_extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Human validation
    human_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Contract renewal chain
    previous_contract_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="contracts")
    validated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[validated_by_id])
    previous_contract: Mapped[Optional["Contract"]] = relationship(
        "Contract",
        remote_side="Contract.id",
        foreign_keys=[previous_contract_id],
    )
    rates: Mapped[List["ContractRate"]] = relationship(
        "ContractRate",
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Contract(id={self.id}, name='{self.name}', supplier_id={self.supplier_id})>"

    @property
    def is_active(self) -> bool:
        today = date.today()
        return self.valid_from <= today <= self.valid_to and self.status == "active"

    @property
    def days_until_expiry(self) -> int:
        return (self.valid_to - date.today()).days


class ContractRate(TenantBase):
    """
    A specific rate within a contract.
    Rates can have seasonal pricing and day-of-week variations.
    """

    __tablename__ = "contract_rates"

    # Contract relationship
    contract_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Service identification
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pax_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # adult, child, etc.

    # Pricing
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    base_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)

    # Seasonal pricing
    season_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    season_start_mmdd: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # MM-DD
    season_end_mmdd: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # MM-DD

    # Day of week restrictions (bitmask: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64)
    day_of_week_mask: Mapped[int] = mapped_column(default=127)  # All days

    # Pax restrictions
    min_pax: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_pax: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Relationships
    contract: Mapped["Contract"] = relationship("Contract", back_populates="rates")

    def __repr__(self) -> str:
        return f"<ContractRate(id={self.id}, service='{self.service_name}', price={self.base_price})>"
