"""
PaxCategory model - configurable traveler categories per tenant.
Supports tourist (adult, teen, child, baby), staff (guide, driver, cook),
and leader (tour_leader) groups with pricing inclusion control.
"""

from typing import Optional

from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class PaxCategory(TenantBase):
    """
    A traveler category within a tenant.

    group_type:
      - tourist: paying travelers (adult, teen, child, baby)
      - staff: operational team (guide, driver, cook)
      - leader: tour leader (costs shared by paying pax, not counted in price/person)

    counts_for_pricing:
      If True, this category is counted when computing price_per_person.
      Tour Leader has counts_for_pricing=False (costs included but split among paying pax).
    """

    __tablename__ = "pax_categories"

    # Identity
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)

    # Classification
    group_type: Mapped[str] = mapped_column(
        String(20), default="tourist"
    )  # tourist, staff, leader

    # Age range (optional, mainly for tourist categories)
    age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Pricing behavior
    counts_for_pricing: Mapped[bool] = mapped_column(Boolean, default=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)

    # Display order
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<PaxCategory(id={self.id}, code='{self.code}', group='{self.group_type}')>"


# Default categories seeded per tenant
DEFAULT_PAX_CATEGORIES = [
    {"code": "adult", "label": "Adulte", "group_type": "tourist", "age_min": 18, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 1},
    {"code": "teen", "label": "Teenager (11-16)", "group_type": "tourist", "age_min": 11, "age_max": 16, "counts_for_pricing": True, "is_system": True, "sort_order": 2},
    {"code": "child", "label": "Enfant (2-10)", "group_type": "tourist", "age_min": 2, "age_max": 10, "counts_for_pricing": True, "is_system": True, "sort_order": 3},
    {"code": "baby", "label": "Bébé (-2 ans)", "group_type": "tourist", "age_min": 0, "age_max": 1, "counts_for_pricing": True, "is_system": True, "sort_order": 4},
    {"code": "tour_leader", "label": "Tour Leader", "group_type": "leader", "age_min": None, "age_max": None, "counts_for_pricing": False, "is_system": True, "sort_order": 5},
    {"code": "guide", "label": "Guide", "group_type": "staff", "age_min": None, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 10},
    {"code": "driver", "label": "Chauffeur", "group_type": "staff", "age_min": None, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 11},
    {"code": "cook", "label": "Cuisinier", "group_type": "staff", "age_min": None, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 12},
]
