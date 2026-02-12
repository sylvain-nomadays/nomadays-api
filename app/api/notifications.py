"""
Notification endpoints — in-app notifications for the current user.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update, func

from app.api.deps import CurrentUser, DbSession
from app.models.notification import Notification

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NotificationItem(BaseModel):
    id: int
    type: str
    title: str
    message: Optional[str] = None
    link: Optional[str] = None
    is_read: bool
    metadata_json: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    updated: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[NotificationItem])
async def list_notifications(
    db: DbSession,
    user: CurrentUser,
):
    """
    List the 50 most recent notifications for the current user.
    Unread notifications appear first, then sorted by newest.
    """
    query = (
        select(Notification)
        .where(
            Notification.tenant_id == user.tenant_id,
            Notification.user_id == user.id,
        )
        .order_by(Notification.is_read.asc(), Notification.created_at.desc())
        .limit(50)
    )

    result = await db.execute(query)
    notifications = result.scalars().all()

    return [NotificationItem.model_validate(n) for n in notifications]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: DbSession,
    user: CurrentUser,
):
    """
    Return the number of unread notifications for the current user.
    """
    query = select(func.count()).where(
        Notification.tenant_id == user.tenant_id,
        Notification.user_id == user.id,
        Notification.is_read == False,
    )

    count = (await db.execute(query)).scalar()

    return UnreadCountResponse(count=count or 0)


@router.patch("/{notification_id}/read", response_model=NotificationItem)
async def mark_notification_read(
    notification_id: int,
    db: DbSession,
    user: CurrentUser,
):
    """
    Mark a single notification as read.
    Verifies that the notification belongs to the current user and tenant.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == user.tenant_id,
            Notification.user_id == user.id,
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.is_read = True
    await db.commit()
    await db.refresh(notification)

    return NotificationItem.model_validate(notification)


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_read(
    db: DbSession,
    user: CurrentUser,
):
    """
    Mark all unread notifications as read for the current user.
    Uses a bulk UPDATE statement for efficiency.
    """
    stmt = (
        update(Notification)
        .where(
            Notification.tenant_id == user.tenant_id,
            Notification.user_id == user.id,
            Notification.is_read == False,
        )
        .values(is_read=True)
    )

    result = await db.execute(stmt)
    await db.commit()

    return MarkAllReadResponse(updated=result.rowcount)
