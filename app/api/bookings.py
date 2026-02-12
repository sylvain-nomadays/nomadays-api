"""
Booking and pre-booking management endpoints.
Handles listing, updating, status changes, and supplier email requests.
"""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import selectinload, load_only

from app.api.deps import CurrentUser, CurrentTenant, DbSession, TenantId
from app.models.booking import Booking
from app.models.supplier import Supplier
from app.models.trip import Trip
from app.models.item import Item
from app.models.formula import Formula
from app.services.email_service import EmailService
from app.services.notification_service import notify_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class BookingListItem(BaseModel):
    id: int
    trip_id: int
    trip_name: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_email: Optional[str] = None
    description: str
    service_date_start: date
    service_date_end: date
    booked_amount: Decimal
    currency: str
    status: str
    is_pre_booking: bool
    confirmation_ref: Optional[str] = None
    requested_by_name: Optional[str] = None
    formula_name: Optional[str] = None
    block_type: Optional[str] = None
    pax_count: Optional[int] = None
    guest_names: Optional[str] = None
    email_sent_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingDetail(BaseModel):
    id: int
    trip_id: int
    trip_name: Optional[str] = None
    item_id: Optional[int] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_email: Optional[str] = None
    cost_nature_id: int
    description: str
    service_date_start: date
    service_date_end: date
    booked_amount: Decimal
    currency: str
    vat_recoverable: bool
    status: str
    confirmation_ref: Optional[str] = None
    is_pre_booking: bool
    requested_by_id: Optional[str] = None
    requested_by_name: Optional[str] = None
    assigned_to_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    email_sent_at: Optional[datetime] = None
    email_sent_to: Optional[str] = None
    supplier_response_note: Optional[str] = None
    formula_id: Optional[int] = None
    formula_name: Optional[str] = None
    block_type: Optional[str] = None
    pax_count: Optional[int] = None
    room_config: Optional[dict] = None
    guest_names: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingUpdate(BaseModel):
    description: Optional[str] = None
    supplier_response_note: Optional[str] = None
    confirmation_ref: Optional[str] = None
    assigned_to_id: Optional[str] = None  # UUID as string


class BookingStatusUpdate(BaseModel):
    status: str
    confirmation_ref: Optional[str] = None
    supplier_response_note: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================

def booking_to_list_item(booking: Booking) -> BookingListItem:
    """Convert a Booking model (with eager-loaded relationships) to BookingListItem."""
    return BookingListItem(
        id=booking.id,
        trip_id=booking.trip_id,
        trip_name=booking.trip.name if booking.trip else None,
        supplier_id=booking.supplier_id,
        supplier_name=booking.supplier.name if booking.supplier else None,
        supplier_email=booking.supplier.reservation_email if booking.supplier else None,
        description=booking.description,
        service_date_start=booking.service_date_start,
        service_date_end=booking.service_date_end,
        booked_amount=booking.booked_amount,
        currency=booking.currency,
        status=booking.status,
        is_pre_booking=booking.is_pre_booking,
        confirmation_ref=booking.confirmation_ref,
        requested_by_name=booking.requested_by.name if booking.requested_by else None,
        formula_name=booking.formula.name if booking.formula else None,
        block_type=booking.formula.block_type if booking.formula else None,
        pax_count=booking.pax_count,
        guest_names=booking.guest_names,
        email_sent_at=booking.email_sent_at,
        created_at=booking.created_at,
    )


def booking_to_detail(booking: Booking) -> BookingDetail:
    """Convert a Booking model (with eager-loaded relationships) to BookingDetail."""
    return BookingDetail(
        id=booking.id,
        trip_id=booking.trip_id,
        trip_name=booking.trip.name if booking.trip else None,
        item_id=booking.item_id,
        supplier_id=booking.supplier_id,
        supplier_name=booking.supplier.name if booking.supplier else None,
        supplier_email=booking.supplier.reservation_email if booking.supplier else None,
        cost_nature_id=booking.cost_nature_id,
        description=booking.description,
        service_date_start=booking.service_date_start,
        service_date_end=booking.service_date_end,
        booked_amount=booking.booked_amount,
        currency=booking.currency,
        vat_recoverable=booking.vat_recoverable,
        status=booking.status,
        confirmation_ref=booking.confirmation_ref,
        is_pre_booking=booking.is_pre_booking,
        requested_by_id=str(booking.requested_by_id) if booking.requested_by_id else None,
        requested_by_name=booking.requested_by.name if booking.requested_by else None,
        assigned_to_id=str(booking.assigned_to_id) if booking.assigned_to_id else None,
        assigned_to_name=booking.assigned_to.name if booking.assigned_to else None,
        email_sent_at=booking.email_sent_at,
        email_sent_to=booking.email_sent_to,
        supplier_response_note=booking.supplier_response_note,
        formula_id=booking.formula_id,
        formula_name=booking.formula.name if booking.formula else None,
        block_type=booking.formula.block_type if booking.formula else None,
        pax_count=booking.pax_count,
        room_config=booking.room_config,
        guest_names=booking.guest_names,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


def _base_booking_query(tenant_id: uuid.UUID):
    """Build a base select query for bookings with standard eager loading."""
    return (
        select(Booking)
        .where(Booking.tenant_id == tenant_id)
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.formula),
        )
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[BookingListItem])
async def list_bookings(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    trip_id: Optional[int] = Query(None, description="Filter by trip"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    is_pre_booking: Optional[bool] = Query(True, description="Filter pre-bookings only"),
    supplier_id: Optional[int] = Query(None, description="Filter by supplier"),
):
    """
    List bookings for the current tenant.
    By default returns only pre-bookings (is_pre_booking=True).
    """
    query = _base_booking_query(tenant.id)

    if trip_id is not None:
        query = query.where(Booking.trip_id == trip_id)

    if status_filter is not None:
        query = query.where(Booking.status == status_filter)

    if is_pre_booking is not None:
        query = query.where(Booking.is_pre_booking == is_pre_booking)

    if supplier_id is not None:
        query = query.where(Booking.supplier_id == supplier_id)

    query = query.order_by(Booking.created_at.desc())

    result = await db.execute(query)
    bookings = result.scalars().all()

    return [booking_to_list_item(b) for b in bookings]


@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Get a specific booking with full details.
    """
    query = (
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant.id,
        )
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )

    result = await db.execute(query)
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    return booking_to_detail(booking)


@router.patch("/{booking_id}", response_model=BookingDetail)
async def update_booking(
    booking_id: int,
    data: BookingUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a booking. Allowed fields: description, supplier_response_note,
    confirmation_ref, assigned_to_id.
    """
    result = await db.execute(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant.id,
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Convert assigned_to_id string to UUID if provided
    if "assigned_to_id" in update_data:
        raw_id = update_data["assigned_to_id"]
        if raw_id is not None:
            try:
                update_data["assigned_to_id"] = uuid.UUID(raw_id)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid assigned_to_id format, must be a valid UUID",
                )
        else:
            update_data["assigned_to_id"] = None

    for field, value in update_data.items():
        setattr(booking, field, value)

    await db.commit()

    # Reload with relationships for response
    query = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    result = await db.execute(query)
    booking = result.scalar_one()

    return booking_to_detail(booking)


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(
    booking_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a booking.
    """
    result = await db.execute(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant.id,
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    await db.delete(booking)
    await db.commit()


@router.post("/{booking_id}/send-request", response_model=BookingDetail)
async def send_booking_request(
    booking_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Send a pre-booking email request to the supplier.
    Updates the booking status to 'sent' and records the email metadata.
    """
    # Load booking with supplier, trip, and formula
    query = (
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant.id,
        )
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    result = await db.execute(query)
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if not booking.supplier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking has no associated supplier",
        )

    if not booking.supplier.reservation_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supplier '{booking.supplier.name}' has no reservation email configured",
        )

    # Send the email
    try:
        email_service = EmailService()
        await email_service.send_pre_booking_request(
            booking=booking,
            supplier=booking.supplier,
            trip=booking.trip,
        )
    except Exception as e:
        logger.error(
            "Failed to send pre-booking email for booking %d to %s: %s",
            booking.id,
            booking.supplier.reservation_email,
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}",
        )

    # Update booking metadata
    booking.status = "sent"
    booking.email_sent_at = datetime.utcnow()
    booking.email_sent_to = booking.supplier.reservation_email

    await db.commit()

    # Reload for response
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    booking = result.scalar_one()

    logger.info(
        "Pre-booking email sent for booking %d to %s",
        booking.id,
        booking.email_sent_to,
    )

    return booking_to_detail(booking)


@router.post("/{booking_id}/send-cancellation", response_model=BookingDetail)
async def send_booking_cancellation(
    booking_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Send a cancellation email to the supplier for a pre-booking.
    The booking must be in 'pending_cancellation' status.
    After sending, the status is changed to 'cancelled'.
    """
    # Load booking with supplier, trip, and formula
    query = (
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant.id,
        )
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    result = await db.execute(query)
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.status != "pending_cancellation":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking must be in 'pending_cancellation' status to send cancellation. Current status: '{booking.status}'",
        )

    if not booking.supplier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking has no associated supplier",
        )

    if not booking.supplier.reservation_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supplier '{booking.supplier.name}' has no reservation email configured",
        )

    # Send the cancellation email
    try:
        email_service = EmailService()
        email_service.send_pre_booking_cancellation(
            booking=booking,
            supplier=booking.supplier,
            trip=booking.trip,
        )
    except Exception as e:
        logger.error(
            "Failed to send cancellation email for booking %d to %s: %s",
            booking.id,
            booking.supplier.reservation_email,
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send cancellation email: {str(e)}",
        )

    # Update booking status to cancelled
    booking.status = "cancelled"

    await db.commit()

    # Notify the requester that the cancellation email was sent
    if booking.requested_by_id:
        supplier_name = booking.supplier.name if booking.supplier else "Fournisseur inconnu"
        try:
            await notify_user(
                db=db,
                user_id=booking.requested_by_id,
                tenant_id=tenant.id,
                type="pre_booking_status",
                title=f"Annulation envoyée — {booking.description}",
                link=f"/admin/circuits/{booking.trip_id}",
                metadata={
                    "booking_id": booking.id,
                    "trip_id": booking.trip_id,
                    "supplier_name": supplier_name,
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to send notification for booking %d cancellation: %s",
                booking.id,
                str(e),
            )

    # Reload for response
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    booking = result.scalar_one()

    logger.info(
        "Cancellation email sent for booking %d to %s",
        booking.id,
        booking.email_sent_to or booking.supplier.reservation_email,
    )

    return booking_to_detail(booking)


@router.patch("/{booking_id}/status", response_model=BookingDetail)
async def update_booking_status(
    booking_id: int,
    data: BookingStatusUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Change the status of a booking. For confirmed/cancelled statuses,
    a notification is sent to the user who requested the pre-booking.
    """
    valid_statuses = {"confirmed", "cancelled", "modified", "declined", "pending_cancellation"}
    if data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    # Load booking with supplier for notification metadata
    query = (
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant.id,
        )
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    result = await db.execute(query)
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # Update booking fields
    booking.status = data.status

    if data.confirmation_ref is not None:
        booking.confirmation_ref = data.confirmation_ref

    if data.supplier_response_note is not None:
        booking.supplier_response_note = data.supplier_response_note

    await db.commit()

    # Send notification to the user who requested the pre-booking
    if data.status in ("confirmed", "cancelled", "declined") and booking.requested_by_id:
        supplier_name = booking.supplier.name if booking.supplier else "Fournisseur inconnu"

        if data.status == "confirmed":
            notif_type = "pre_booking_status"
            title = f"Pré-réservation confirmée — {booking.description}"
        elif data.status == "declined":
            notif_type = "pre_booking_status"
            title = f"Pré-réservation refusée — {booking.description}"
        else:  # cancelled
            notif_type = "pre_booking_status"
            title = f"Pré-réservation annulée — {booking.description}"

        try:
            await notify_user(
                db=db,
                user_id=booking.requested_by_id,
                tenant_id=tenant.id,
                type=notif_type,
                title=title,
                link=f"/admin/circuits/{booking.trip_id}",
                metadata={
                    "booking_id": booking.id,
                    "trip_id": booking.trip_id,
                    "supplier_name": supplier_name,
                },
            )
        except Exception as e:
            # Notification failure should not block the status change
            logger.warning(
                "Failed to send notification for booking %d status change: %s",
                booking.id,
                str(e),
            )

    # Reload for response
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.supplier),
            selectinload(Booking.trip).load_only(Trip.name),
            selectinload(Booking.requested_by),
            selectinload(Booking.assigned_to),
            selectinload(Booking.formula),
        )
    )
    booking = result.scalar_one()

    logger.info(
        "Booking %d status changed to '%s' by user %s",
        booking.id,
        data.status,
        user.id,
    )

    return booking_to_detail(booking)
