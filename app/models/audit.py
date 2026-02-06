"""
Audit Log model - tracks all changes for compliance.
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, String, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(TenantBase):
    """
    Audit log entry tracking changes to entities.
    """

    __tablename__ = "audit_log"

    # User who made the change
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Entity reference
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Table name
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Action type
    action: Mapped[str] = mapped_column(
        SQLEnum(
            "create",
            "update",
            "delete",
            "sync_from_template",
            "sync_to_template",
            "override",
            name="audit_action_enum"
        ),
        nullable=False,
    )

    # Change details
    old_values_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_values_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Context
    context: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, entity={self.entity_type}:{self.entity_id}, action='{self.action}')>"


# Import at end to avoid circular imports
from app.models.user import User
