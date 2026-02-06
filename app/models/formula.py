"""
Formula and Condition models.
Formulas group items within a trip day.
Conditions allow items to be conditionally included.
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import TripDay, Trip
    from app.models.item import Item


class Formula(TenantBase):
    """
    A formula groups related items within a trip day.
    Examples: "Visit Elephant Haven", "Transfer to Kanchanaburi"
    """

    __tablename__ = "formulas"

    # Trip day relationship
    trip_day_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trip_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Service period (relative to trip start)
    service_day_start: Mapped[int] = mapped_column(Integer, default=1)
    service_day_end: Mapped[int] = mapped_column(Integer, default=1)

    # Template tracking
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    template_source_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("formulas.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    trip_day: Mapped["TripDay"] = relationship("TripDay", back_populates="formulas")
    template_source: Mapped[Optional["Formula"]] = relationship(
        "Formula",
        remote_side="Formula.id",
        foreign_keys=[template_source_id],
    )
    items: Mapped[List["Item"]] = relationship(
        "Item",
        back_populates="formula",
        cascade="all, delete-orphan",
        order_by="Item.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Formula(id={self.id}, name='{self.name}')>"

    @property
    def service_days_count(self) -> int:
        """Number of days this formula spans."""
        return self.service_day_end - self.service_day_start + 1


class Condition(TenantBase):
    """
    A condition that can enable/disable items.
    Examples: "Guide francophone", "Vol inclus"
    """

    __tablename__ = "conditions"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip")

    def __repr__(self) -> str:
        return f"<Condition(id={self.id}, name='{self.name}', active={self.is_active})>"


# Import at end to avoid circular imports
from app.models.trip import TripDay, Trip
from app.models.item import Item
