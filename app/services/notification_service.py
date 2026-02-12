"""
Notification service for Nomadays.

Provides helpers to create in-app notifications for individual users
or groups of users (e.g. the logistics / management team).
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Notification:
    """
    Create a single in-app notification for a user.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant UUID (multi-tenant isolation).
        user_id: Recipient user UUID.
        type: Notification type (e.g. "pre_booking_status", "task_assigned").
        title: Short notification title.
        message: Optional longer description.
        link: Optional in-app link for the notification.
        metadata: Optional JSON metadata (trip_id, booking_id, etc.).

    Returns:
        The created Notification instance (already flushed with an id).
    """
    notification = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
        metadata_json=metadata,
        is_read=False,
    )
    db.add(notification)
    await db.flush()

    logger.info(
        "Notification created: type=%s user_id=%s title=%s",
        type,
        user_id,
        title,
    )
    return notification


async def notify_user(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Notification:
    """
    Send an in-app notification to a single user.

    This is a convenience alias for :func:`create_notification`.
    """
    return await create_notification(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
        metadata=metadata,
    )


async def notify_logistics_team(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> list[Notification]:
    """
    Send an in-app notification to every manager / admin for the given tenant.

    Targets users whose role is ``dmc_manager`` or ``admin_nomadays``
    and who are currently active.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant UUID.
        type: Notification type.
        title: Short notification title.
        message: Optional longer description.
        link: Optional in-app link.
        metadata: Optional JSON metadata.

    Returns:
        List of created Notification instances.
    """
    # Find all active managers / admins for this tenant
    stmt = (
        select(User)
        .where(
            User.tenant_id == tenant_id,
            User.role.in_(["dmc_manager", "admin_nomadays"]),
            User.is_active == True,  # noqa: E712 — SQLAlchemy requires == for filters
        )
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    if not users:
        logger.warning(
            "notify_logistics_team: no active dmc_manager/admin_nomadays "
            "found for tenant_id=%s",
            tenant_id,
        )
        return []

    notifications: list[Notification] = []
    for user in users:
        notification = await create_notification(
            db=db,
            tenant_id=tenant_id,
            user_id=user.id,
            type=type,
            title=title,
            message=message,
            link=link,
            metadata=metadata,
        )
        notifications.append(notification)

    logger.info(
        "notify_logistics_team: %d notifications created for tenant_id=%s",
        len(notifications),
        tenant_id,
    )
    return notifications
