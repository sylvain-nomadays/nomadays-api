"""
User model with role-based access control.
Maps to existing users table with UUID ids.
"""

import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Boolean, ForeignKey, Enum as SQLEnum, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class User(Base, TimestampMixin):
    """
    A user belonging to a tenant with role-based permissions.
    Maps to existing users table with UUID primary key.
    """

    __tablename__ = "users"

    # Use UUID to match existing table
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Tenant relationship (UUID)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity (existing columns from DB)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Role-based access control (existing enum in DB)
    role: Mapped[str] = mapped_column(
        SQLEnum(
            "admin_nomadays",
            "support_nomadays",
            "dmc_manager",
            "dmc_seller",
            "dmc_accountant",
            "client_direct",
            "agency_b2b",
            name="user_role",
            create_type=False,  # Don't create, it exists
        ),
        default="dmc_seller",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    last_login_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"

    @property
    def name(self) -> str:
        """Full name from first_name and last_name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.email

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin_nomadays", "dmc_manager")

    @property
    def can_edit_trips(self) -> bool:
        return self.role in ("admin_nomadays", "support_nomadays", "dmc_manager", "dmc_seller")

    @property
    def can_manage_contracts(self) -> bool:
        return self.role in ("admin_nomadays", "dmc_manager")

    @property
    def can_view_financials(self) -> bool:
        return self.role in ("admin_nomadays", "dmc_manager", "dmc_accountant")
