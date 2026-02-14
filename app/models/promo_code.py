"""
Promo code models — centralized discount system (not per-tenant).

Supports fixed-amount and percentage discounts with usage limits and date ranges.
Applied on the public invoice page before payment.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, String, Date, DateTime, Integer, Numeric, Text, Boolean,
    ForeignKey, Enum as SQLEnum, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PromoCode(Base):
    """
    A promo code or discount voucher.
    Centralized across all tenants (Nomadays-level).
    """

    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Discount config
    discount_type: Mapped[str] = mapped_column(
        SQLEnum("fixed", "percentage", name="promo_discount_type_enum", create_type=False),
        nullable=False,
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")  # for fixed only
    min_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default="0")

    # Usage limits
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # null = unlimited
    current_uses: Mapped[int] = mapped_column(Integer, server_default="0")

    # Validity window
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relationships
    usages: Mapped[list["PromoCodeUsage"]] = relationship(
        "PromoCodeUsage", back_populates="promo_code", cascade="all, delete-orphan",
    )

    def is_valid(self, invoice_amount: Decimal | None = None) -> tuple[bool, str]:
        """Check if promo code can be applied. Returns (valid, error_message)."""
        if not self.is_active:
            return False, "Code promo désactivé"

        today = date.today()
        if self.valid_from and today < self.valid_from:
            return False, "Code promo pas encore valide"
        if self.valid_until and today > self.valid_until:
            return False, "Code promo expiré"

        if self.max_uses is not None and self.current_uses >= self.max_uses:
            return False, "Code promo épuisé (utilisation maximale atteinte)"

        if invoice_amount is not None and invoice_amount < self.min_amount:
            return False, f"Montant minimum de {self.min_amount} € requis"

        return True, ""

    def calculate_discount(self, amount: Decimal) -> Decimal:
        """Calculate the discount amount for a given invoice total."""
        if self.discount_type == "fixed":
            # Don't exceed the invoice total
            return min(self.discount_value, amount)
        elif self.discount_type == "percentage":
            discount = (amount * self.discount_value / Decimal("100")).quantize(Decimal("0.01"))
            return min(discount, amount)
        return Decimal("0")

    def __repr__(self) -> str:
        return f"<PromoCode(id={self.id}, code='{self.code}', type='{self.discount_type}')>"


class PromoCodeUsage(Base):
    """Tracks each use of a promo code on an invoice (audit trail)."""

    __tablename__ = "promo_code_usages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    promo_code_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("promo_codes.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relationships
    promo_code: Mapped["PromoCode"] = relationship("PromoCode", back_populates="usages")

    def __repr__(self) -> str:
        return f"<PromoCodeUsage(promo={self.promo_code_id}, invoice={self.invoice_id}, amount={self.discount_amount})>"
