"""
Formula model.
Formulas group items within a trip day or at trip level (transversal).
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import TripDay, Trip
    from app.models.item import Item
    from app.models.condition import Condition
    from app.models.location import Location


class Formula(TenantBase):
    """
    A formula groups related items within a trip day or at the trip level.

    Day-level formulas (is_transversal=False):
        Linked via trip_day_id. Examples: "Visit Elephant Haven", "Transfer to Kanchanaburi"

    Transversal formulas (is_transversal=True):
        Linked via trip_id. Examples: "Guide francophone J1-J10", "Chauffeur", "Budget Cadeau"
    """

    __tablename__ = "formulas"

    # Trip day relationship (for day-level formulas)
    trip_day_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trip_days.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Trip relationship (for transversal formulas — direct link, not through TripDay)
    trip_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_transversal: Mapped[bool] = mapped_column(Boolean, default=False)

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Service period (relative to trip start) — nullable for trip-level forfait items
    service_day_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=1)
    service_day_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=1)

    # Template tracking
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    template_source_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("formulas.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Template versioning & metadata (used when is_template=True or when linked to a template)
    template_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    template_source_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    template_tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    template_location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Block system
    block_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="activity"
    )  # 'text', 'activity', 'accommodation', 'transport'

    # Conditional inclusion: link formula to a condition
    # Declares that this formula's items are governed by this condition
    # (e.g., "Langue du guide"). Individual items carry condition_option_id.
    condition_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("conditions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    parent_block_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("formulas.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Relationships
    trip_day: Mapped[Optional["TripDay"]] = relationship("TripDay", back_populates="formulas")
    trip: Mapped[Optional["Trip"]] = relationship(
        "Trip",
        back_populates="transversal_formulas",
        foreign_keys=[trip_id],
    )
    template_source: Mapped[Optional["Formula"]] = relationship(
        "Formula",
        remote_side="Formula.id",
        foreign_keys=[template_source_id],
    )
    # Block hierarchy (parent/children)
    # lazy="noload" avoids async lazy-load errors — use selectinload() when needed
    parent_block: Mapped[Optional["Formula"]] = relationship(
        "Formula",
        remote_side="Formula.id",
        foreign_keys=[parent_block_id],
        back_populates="children",
        lazy="noload",
    )
    children: Mapped[List["Formula"]] = relationship(
        "Formula",
        foreign_keys="Formula.parent_block_id",
        back_populates="parent_block",
        cascade="all, delete-orphan",
        order_by="Formula.sort_order",
        lazy="noload",
    )
    items: Mapped[List["Item"]] = relationship(
        "Item",
        back_populates="formula",
        cascade="all, delete-orphan",
        order_by="Item.sort_order",
    )
    condition: Mapped[Optional["Condition"]] = relationship("Condition")
    template_location: Mapped[Optional["Location"]] = relationship(
        "Location",
        foreign_keys=[template_location_id],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Formula(id={self.id}, name='{self.name}')>"

    @property
    def service_days_count(self) -> int:
        """Number of days this formula spans. Returns 1 for trip-level forfait."""
        if self.service_day_start is None or self.service_day_end is None:
            return 1
        return self.service_day_end - self.service_day_start + 1


# Import at end to avoid circular imports
from app.models.trip import TripDay, Trip
from app.models.item import Item
from app.models.condition import Condition
from app.models.location import Location
