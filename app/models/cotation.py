"""
TripCotation model — Named quotation profiles for a trip.

A cotation represents a specific pricing scenario with:
- A set of condition selections (e.g., "Budget hotel", "French-speaking guide")
- Auto-generated pax configurations from min_pax to max_pax (mode "range")
- Or a fixed composition (e.g. 2 adults + 1 child) (mode "custom")
- Stored calculation results after running the quotation engine
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import Trip


class TripCotation(TenantBase):
    """
    A named quotation profile for a trip.

    Each cotation stores:
    - mode: "range" (grid min→max adults) or "custom" (fixed composition)
    - condition_selections_json: overrides for trip-level conditions
      e.g. {"5": 12, "8": 34} → condition_id 5 selects option 12, condition_id 8 selects option 34
    - pax_configs_json: auto-generated pax configurations
      e.g. [{"label": "2 pax", "adult": 2, "guide": 1, "driver": 1, "dbl": 1, "sgl": 0, "total_pax": 4}, ...]
    - room_demand_override_json: optional room override per cotation
      e.g. [{"bed_type": "FAM", "qty": 1}, {"bed_type": "SGL", "qty": 1}]
    - results_json: full calculation results (stored after calculation)
    """

    __tablename__ = "trip_cotations"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Mode: "range" (grid min→max) or "custom" (fixed composition)
    mode: Mapped[str] = mapped_column(String(20), default="range")

    # Condition overrides: {condition_id: selected_option_id}
    # If a condition is NOT in this map, the trip-level TripCondition applies.
    # If a condition IS in this map, it overrides the trip-level selection for this cotation.
    condition_selections_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Pax range for auto-generation (mode "range")
    min_pax: Mapped[int] = mapped_column(Integer, default=2)
    max_pax: Mapped[int] = mapped_column(Integer, default=10)

    # Auto-generated pax configs (list of dicts)
    # Each entry: {"label": "2 pax", "adult": 2, "guide": 1, "driver": 1, "dbl": 1, "sgl": 0, "total_pax": 4}
    pax_configs_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Room demand override (optional, overrides trip.room_demand_json for this cotation)
    # e.g. [{"bed_type": "FAM", "qty": 1}, {"bed_type": "SGL", "qty": 1}]
    room_demand_override_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Calculation results (full breakdown stored after calculation)
    results_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Tarification (public pricing attached to this cotation)
    # Stores: {"mode": "range_web|per_person|per_group|service_list|enumeration", "entries": [...]}
    tarification_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="draft"
    )  # draft, calculating, calculated, error

    calculated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="cotations")

    def __repr__(self) -> str:
        return f"<TripCotation(id={self.id}, name='{self.name}', mode='{self.mode}', status='{self.status}')>"
