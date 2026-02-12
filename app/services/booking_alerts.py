"""
Booking alerts service — check for pre-bookings awaiting supplier response.

Provides helpers to:
- Calculate business-hours deadlines (48h by default)
- Find overdue pre-bookings (no supplier response past deadline)
- Create alert notifications for overdue bookings
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking
from app.models.user import User
from app.services.notification_service import notify_user

logger = logging.getLogger(__name__)

# Default deadline: 48 business hours (~2 working days of 8h = 6 calendar days to be safe)
DEFAULT_DEADLINE_HOURS = 48
BUSINESS_HOURS_PER_DAY = 8


def calculate_business_deadline(
    from_dt: datetime,
    business_hours: int = DEFAULT_DEADLINE_HOURS,
) -> datetime:
    """
    Calculate a deadline in business hours from a given datetime.

    Business hours = Mon-Fri 09:00-18:00 (9h/day).
    48 business hours ≈ ~5.3 working days ≈ roughly 1 week with weekends.

    For simplicity, we approximate:
    - 48 business hours = 6 calendar days (conservative)
    - This avoids complex timezone/holiday calculations
    """
    # Simple approximation: business_hours / 8h per day = working days
    # Add ~40% buffer for weekends (5 working days in 7 calendar days)
    working_days = business_hours / BUSINESS_HOURS_PER_DAY
    calendar_days = int(working_days * 7 / 5)  # Scale up for weekends
    return from_dt + timedelta(days=max(calendar_days, 1))


async def get_overdue_prebookings(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    deadline_hours: int = DEFAULT_DEADLINE_HOURS,
) -> list[Booking]:
    """
    Find all pre-bookings that are still 'pending' past their deadline.

    A booking is overdue if:
    - is_pre_booking = true
    - status = 'pending' (no response yet)
    - created_at + deadline < now
    """
    from sqlalchemy import text as sa_text

    deadline_threshold = datetime.utcnow() - timedelta(
        days=int(deadline_hours / BUSINESS_HOURS_PER_DAY * 7 / 5)
    )

    result = await db.execute(
        select(Booking)
        .where(
            Booking.tenant_id == tenant_id,
            Booking.is_pre_booking.is_(True),
            sa_text("bookings.status = 'pending'"),
            Booking.created_at <= deadline_threshold,
        )
        .options(
            selectinload(Booking.trip),
            selectinload(Booking.supplier),
            selectinload(Booking.requested_by),
        )
    )
    return list(result.scalars().all())


async def check_and_notify_overdue(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    deadline_hours: int = DEFAULT_DEADLINE_HOURS,
) -> int:
    """
    Check for overdue pre-bookings and send reminder notifications.

    Returns the number of notifications sent.
    """
    overdue = await get_overdue_prebookings(db, tenant_id, deadline_hours)
    if not overdue:
        return 0

    count = 0
    for booking in overdue:
        # Notify the person who requested the pre-booking
        if booking.requested_by_id:
            try:
                trip_name = booking.trip.name if booking.trip else "Circuit"
                supplier_name = booking.supplier.name if booking.supplier else "Fournisseur"
                days_waiting = (datetime.utcnow() - booking.created_at).days

                await notify_user(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=booking.requested_by_id,
                    type="pre_booking_request",
                    title=f"Relance pré-réservation — {supplier_name}",
                    message=(
                        f"La demande de pré-réservation pour {booking.description} "
                        f"({trip_name}) est en attente depuis {days_waiting} jour(s). "
                        f"Aucune réponse du fournisseur."
                    ),
                    link=f"/admin/reservations?trip_id={booking.trip_id}",
                    metadata={
                        "booking_id": booking.id,
                        "trip_id": booking.trip_id,
                        "supplier_name": supplier_name,
                        "days_waiting": days_waiting,
                        "alert_type": "overdue_prebooking",
                    },
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to send overdue alert for booking {booking.id}: {e}")

    if count > 0:
        await db.commit()
        logger.info(f"Sent {count} overdue pre-booking alerts for tenant {tenant_id}")

    return count
