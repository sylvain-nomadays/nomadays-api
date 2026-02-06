"""
Tenant model - represents a DMC (Destination Management Company).
Each tenant has isolated data and configurable settings.
NOTE: This model maps to the existing 'tenants' table with UUID ids.
"""

import uuid
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, DECIMAL, JSON, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.supplier import Supplier
    from app.models.dossier import Dossier


class Tenant(Base, TimestampMixin):
    """
    A DMC (Destination Management Company) tenant.
    All data is isolated per tenant.
    Maps to existing tenants table with UUID primary key.
    """

    __tablename__ = "tenants"

    # Use UUID to match existing table
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Identity (existing columns)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    # Existing columns
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legal_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="tenant")
    suppliers: Mapped[List["Supplier"]] = relationship("Supplier", back_populates="tenant")
    dossiers: Mapped[List["Dossier"]] = relationship("Dossier", back_populates="tenant")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', slug='{self.slug}')>"
