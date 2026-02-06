"""
Dashboard endpoints - statistics and overview data.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select, func, and_

from app.api.deps import DbSession, CurrentTenant
from app.models.trip import Trip
from app.models.supplier import Supplier
from app.models.contract import Contract
from app.models.booking import Booking
from app.models.alert import AIAlert

router = APIRouter()


class DashboardStats(BaseModel):
    # Trips
    total_trips: int
    template_count: int
    client_trips_count: int
    draft_trips: int
    confirmed_trips: int

    # Suppliers
    total_suppliers: int
    active_suppliers: int

    # Contracts
    total_contracts: int
    expiring_soon_contracts: int  # Within 30 days

    # Bookings
    pending_bookings: int
    confirmed_bookings: int
    total_booking_value: float

    # Alerts
    unacknowledged_alerts: int
    critical_alerts: int


class RecentActivity(BaseModel):
    type: str  # "trip_created", "booking_confirmed", "alert_raised", etc.
    entity_id: int
    entity_name: str
    timestamp: datetime
    description: str


class DashboardResponse(BaseModel):
    stats: DashboardStats
    recent_trips: list
    expiring_contracts: list
    pending_bookings: list


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get key statistics for the dashboard.
    """
    # Trips stats
    total_trips = (await db.execute(
        select(func.count()).where(Trip.tenant_id == tenant.id)
    )).scalar()

    template_count = (await db.execute(
        select(func.count()).where(
            Trip.tenant_id == tenant.id,
            Trip.type == "template",
        )
    )).scalar()

    client_trips = (await db.execute(
        select(func.count()).where(
            Trip.tenant_id == tenant.id,
            Trip.type == "client",
        )
    )).scalar()

    draft_trips = (await db.execute(
        select(func.count()).where(
            Trip.tenant_id == tenant.id,
            Trip.status == "draft",
        )
    )).scalar()

    confirmed_trips = (await db.execute(
        select(func.count()).where(
            Trip.tenant_id == tenant.id,
            Trip.status == "confirmed",
        )
    )).scalar()

    # Suppliers stats
    total_suppliers = (await db.execute(
        select(func.count()).where(Supplier.tenant_id == tenant.id)
    )).scalar()

    active_suppliers = (await db.execute(
        select(func.count()).where(
            Supplier.tenant_id == tenant.id,
            Supplier.is_active == True,
        )
    )).scalar()

    # Contracts stats
    total_contracts = (await db.execute(
        select(func.count()).where(Contract.tenant_id == tenant.id)
    )).scalar()

    thirty_days_from_now = datetime.utcnow().date() + timedelta(days=30)
    expiring_contracts = (await db.execute(
        select(func.count()).where(
            Contract.tenant_id == tenant.id,
            Contract.valid_to <= thirty_days_from_now,
            Contract.valid_to >= datetime.utcnow().date(),
        )
    )).scalar()

    # Bookings stats
    pending_bookings = (await db.execute(
        select(func.count()).where(
            Booking.tenant_id == tenant.id,
            Booking.status == "pending",
        )
    )).scalar()

    confirmed_bookings = (await db.execute(
        select(func.count()).where(
            Booking.tenant_id == tenant.id,
            Booking.status == "confirmed",
        )
    )).scalar()

    booking_value_result = (await db.execute(
        select(func.coalesce(func.sum(Booking.total_cost), 0)).where(
            Booking.tenant_id == tenant.id,
            Booking.status.in_(["pending", "confirmed"]),
        )
    )).scalar()

    # Alerts stats
    unack_alerts = (await db.execute(
        select(func.count()).where(
            AIAlert.tenant_id == tenant.id,
            AIAlert.acknowledged == False,
        )
    )).scalar()

    critical_alerts = (await db.execute(
        select(func.count()).where(
            AIAlert.tenant_id == tenant.id,
            AIAlert.acknowledged == False,
            AIAlert.severity == "critical",
        )
    )).scalar()

    return DashboardStats(
        total_trips=total_trips or 0,
        template_count=template_count or 0,
        client_trips_count=client_trips or 0,
        draft_trips=draft_trips or 0,
        confirmed_trips=confirmed_trips or 0,
        total_suppliers=total_suppliers or 0,
        active_suppliers=active_suppliers or 0,
        total_contracts=total_contracts or 0,
        expiring_soon_contracts=expiring_contracts or 0,
        pending_bookings=pending_bookings or 0,
        confirmed_bookings=confirmed_bookings or 0,
        total_booking_value=float(booking_value_result or 0),
        unacknowledged_alerts=unack_alerts or 0,
        critical_alerts=critical_alerts or 0,
    )


@router.get("/recent-trips")
async def get_recent_trips(
    db: DbSession,
    tenant: CurrentTenant,
    limit: int = 10,
):
    """
    Get recently updated trips.
    """
    result = await db.execute(
        select(Trip)
        .where(Trip.tenant_id == tenant.id)
        .order_by(Trip.updated_at.desc())
        .limit(limit)
    )
    trips = result.scalars().all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "type": t.type,
            "status": t.status,
            "client_name": t.client_name,
            "start_date": t.start_date,
            "updated_at": t.updated_at,
        }
        for t in trips
    ]


@router.get("/expiring-contracts")
async def get_expiring_contracts(
    db: DbSession,
    tenant: CurrentTenant,
    days: int = 30,
):
    """
    Get contracts expiring within N days.
    """
    future_date = datetime.utcnow().date() + timedelta(days=days)

    result = await db.execute(
        select(Contract)
        .where(
            Contract.tenant_id == tenant.id,
            Contract.valid_to <= future_date,
            Contract.valid_to >= datetime.utcnow().date(),
        )
        .order_by(Contract.valid_to.asc())
    )
    contracts = result.scalars().all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "supplier_id": c.supplier_id,
            "valid_to": c.valid_to,
            "days_remaining": (c.valid_to - datetime.utcnow().date()).days,
        }
        for c in contracts
    ]


@router.get("/pending-bookings")
async def get_pending_bookings(
    db: DbSession,
    tenant: CurrentTenant,
    limit: int = 20,
):
    """
    Get pending bookings requiring attention.
    """
    result = await db.execute(
        select(Booking)
        .where(
            Booking.tenant_id == tenant.id,
            Booking.status == "pending",
        )
        .order_by(Booking.created_at.desc())
        .limit(limit)
    )
    bookings = result.scalars().all()

    return [
        {
            "id": b.id,
            "item_id": b.item_id,
            "supplier_id": b.supplier_id,
            "status": b.status,
            "total_cost": float(b.total_cost) if b.total_cost else 0,
            "service_date": b.service_date,
            "created_at": b.created_at,
        }
        for b in bookings
    ]
