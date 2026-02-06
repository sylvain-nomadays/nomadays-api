"""
Booking and PaymentSchedule models - generated after trip confirmation.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, Boolean, DECIMAL, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import Trip
    from app.models.item import Item
    from app.models.supplier import Supplier
    from app.models.cost_nature import CostNature


class Booking(TenantBase):
    """
    A booking (supplier reservation) generated from confirmed trip items.
    """

    __tablename__ = "bookings"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source item (optional - can be manual booking)
    item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Supplier
    supplier_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Cost nature
    cost_nature_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cost_natures.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Booking details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    service_date_start: Mapped[date] = mapped_column(Date, nullable=False)
    service_date_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Financials
    booked_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    vat_recoverable: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "pending",
            "sent",
            "confirmed",
            "modified",
            "cancelled",
            name="booking_status_enum"
        ),
        default="pending",
    )

    # Supplier confirmation
    confirmation_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip")
    item: Mapped[Optional["Item"]] = relationship("Item")
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier")
    cost_nature: Mapped["CostNature"] = relationship("CostNature")

    def __repr__(self) -> str:
        return f"<Booking(id={self.id}, description='{self.description}', status='{self.status}')>"


class PaymentSchedule(TenantBase):
    """
    A scheduled payment for a booking.
    """

    __tablename__ = "payment_schedule"

    # Booking relationship
    booking_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Payment details
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Type
    type: Mapped[str] = mapped_column(
        SQLEnum(
            "deposit",
            "balance",
            "full",
            "installment",
            name="payment_type_enum"
        ),
        default="full",
    )

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "pending",
            "due_soon",
            "overdue",
            "paid",
            "cancelled",
            name="payment_status_enum"
        ),
        default="pending",
    )

    # Payment tracking
    paid_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    paid_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    payment_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking")

    def __repr__(self) -> str:
        return f"<PaymentSchedule(id={self.id}, due={self.due_date}, amount={self.amount}, status='{self.status}')>"


# Import at end to avoid circular imports
from app.models.trip import Trip
from app.models.item import Item
from app.models.supplier import Supplier
from app.models.cost_nature import CostNature
