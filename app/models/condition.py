"""
Condition models for conditional item inclusion.

Conditions are global templates (tenant-level) with options/values.
At the trip level, TripCondition activates a condition and selects an option.
At the formula level, condition_id declares which condition governs the formula.
At the item level, condition_option_id links to a specific option.

Example:
  Condition "Guide language" → options: Français, Anglais, Allemand, Espagnol
  TripCondition: trip=123, condition="Guide language", selected_option="Français", is_active=True
  Formula "Guide" → condition_id → "Guide language"
  Item "Guide francophone" → condition_option_id → "Français" → included
  Item "Guide anglophone" → condition_option_id → "Anglais" → excluded
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import Trip


class Condition(TenantBase):
    """
    A global condition template (tenant-level) with options.
    Examples: "Guide language", "Cook included", "Vehicle type"
    """

    __tablename__ = "conditions"

    # Legacy: trip_id is now nullable (was NOT NULL before migration 044)
    # Kept in DB for backwards compatibility. Should be NULL for new conditions.
    trip_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Scope: 'all' (default), 'accommodation', 'service'
    # Used to filter which conditions appear in specific UI contexts
    applies_to: Mapped[str] = mapped_column(String(50), nullable=False, server_default="all")

    # Legacy: is_active is now managed via TripCondition per circuit.
    # Kept in DB for backwards compatibility.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    options: Mapped[List["ConditionOption"]] = relationship(
        "ConditionOption",
        back_populates="condition",
        cascade="all, delete-orphan",
        order_by="ConditionOption.sort_order",
    )
    trip_conditions: Mapped[List["TripCondition"]] = relationship(
        "TripCondition",
        back_populates="condition",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Condition(id={self.id}, name='{self.name}')>"


class ConditionOption(TenantBase):
    """
    A possible value/option for a condition.
    Examples: "Français", "Anglais", "Avec cuisinier", "Sans cuisinier"
    """

    __tablename__ = "condition_options"

    # Condition FK
    condition_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conditions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    condition: Mapped["Condition"] = relationship("Condition", back_populates="options")

    def __repr__(self) -> str:
        return f"<ConditionOption(id={self.id}, label='{self.label}')>"


class TripCondition(TenantBase):
    """
    Activation of a condition for a specific trip, with selected option.
    Unique per (trip_id, condition_id).
    """

    __tablename__ = "trip_conditions"
    __table_args__ = (
        UniqueConstraint("trip_id", "condition_id", name="uq_trip_conditions_trip_condition"),
    )

    # Trip FK
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Condition FK (tenant-level condition template)
    condition_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conditions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Selected option (which value is chosen for this trip)
    selected_option_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("condition_options.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Toggle: condition can be deactivated without removing the selection
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="trip_conditions")
    condition: Mapped["Condition"] = relationship("Condition", back_populates="trip_conditions")
    selected_option: Mapped[Optional["ConditionOption"]] = relationship("ConditionOption")

    def __repr__(self) -> str:
        return f"<TripCondition(id={self.id}, trip_id={self.trip_id}, condition_id={self.condition_id}, active={self.is_active})>"


# Import at end to avoid circular imports
from app.models.trip import Trip
