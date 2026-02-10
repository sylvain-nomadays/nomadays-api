"""
Trip/Circuit management endpoints.
"""

import io
import logging
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant, get_current_user, get_current_tenant
from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.trip import Trip, TripDay, TripPaxConfig
from app.models.trip_photo import TripPhoto
from app.models.formula import Formula
from app.models.condition import TripCondition
from app.models.item import Item
from app.services.storage import validate_file, get_mime_type
from app.services.image_processor import process_image, save_as_avif
from app.services.circuit_image_generator import upload_seo_image, slugify, COUNTRY_DESTINATIONS, build_prompt
from app.services.vertex_ai import get_image_generation_service

logger = logging.getLogger(__name__)
router = APIRouter()


# Schemas
class TripCreate(BaseModel):
    name: str
    type: str = "template"  # online, gir, template, custom
    master_trip_id: Optional[int] = None  # For GIR: link to online master
    is_published: bool = False  # For online circuits
    template_id: Optional[int] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: int = 1
    destination_country: Optional[str] = None
    default_currency: str = "EUR"
    margin_pct: float = 30.0
    margin_type: str = "margin"


class TripUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    master_trip_id: Optional[int] = None
    is_published: Optional[bool] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: Optional[int] = None
    destination_country: Optional[str] = None
    default_currency: Optional[str] = None
    margin_pct: Optional[float] = None
    margin_type: Optional[str] = None
    vat_pct: Optional[float] = None
    operator_commission_pct: Optional[float] = None
    currency_rates_json: Optional[dict] = None
    status: Optional[str] = None
    # Presentation fields
    description_short: Optional[str] = None
    description_tone: Optional[str] = None
    highlights: Optional[List[dict]] = None
    inclusions: Optional[List[dict]] = None
    exclusions: Optional[List[dict]] = None
    info_general: Optional[str] = None
    info_formalities: Optional[str] = None
    info_booking_conditions: Optional[str] = None
    info_cancellation_policy: Optional[str] = None
    info_additional: Optional[str] = None
    # Language for translation
    language: Optional[str] = None


class TripSummaryResponse(BaseModel):
    id: int
    tenant_id: UUID
    name: str
    reference: Optional[str]
    type: str
    status: str
    master_trip_id: Optional[int]
    is_published: bool
    client_name: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    duration_days: int
    destination_country: Optional[str]
    locations_summary: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TripDayResponse(BaseModel):
    id: int
    day_number: int
    day_number_end: Optional[int] = None
    title: Optional[str]
    description: Optional[str]
    location_from: Optional[str]
    location_to: Optional[str]
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    overnight_city: Optional[str] = None
    sort_order: int
    breakfast_included: bool = False
    lunch_included: bool = False
    dinner_included: bool = False

    class Config:
        from_attributes = True


class TripDayCreate(BaseModel):
    day_number: Optional[int] = None  # Auto-calculated if not provided
    day_number_end: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location_from: Optional[str] = None
    location_to: Optional[str] = None
    location_id: Optional[int] = None
    breakfast_included: bool = False
    lunch_included: bool = False
    dinner_included: bool = False


class TripDayUpdate(BaseModel):
    day_number: Optional[int] = None
    day_number_end: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location_from: Optional[str] = None
    location_to: Optional[str] = None
    location_id: Optional[int] = None
    breakfast_included: Optional[bool] = None
    lunch_included: Optional[bool] = None
    dinner_included: Optional[bool] = None


class TripPaxConfigResponse(BaseModel):
    id: int
    label: str
    total_pax: int
    args_json: dict
    margin_override_pct: Optional[float]
    total_cost: float
    total_price: float
    total_profit: float
    cost_per_person: float
    price_per_person: float

    class Config:
        from_attributes = True


class TripResponse(BaseModel):
    id: int
    tenant_id: UUID
    name: str
    reference: Optional[str]
    type: str
    master_trip_id: Optional[int]
    is_published: bool
    template_id: Optional[int]
    client_name: Optional[str]
    client_email: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    duration_days: int
    destination_country: Optional[str]
    default_currency: str
    margin_pct: float
    margin_type: str
    vat_pct: float
    operator_commission_pct: float
    currency_rates_json: Optional[dict]
    status: str
    version: int
    days: List[TripDayResponse] = []
    pax_configs: List[TripPaxConfigResponse] = []
    formulas: List[dict] = []
    # Presentation fields
    description_short: Optional[str] = None
    description_tone: Optional[str] = None
    highlights: Optional[List[dict]] = None
    inclusions: Optional[List[dict]] = None
    exclusions: Optional[List[dict]] = None
    info_general: Optional[str] = None
    info_formalities: Optional[str] = None
    info_booking_conditions: Optional[str] = None
    info_cancellation_policy: Optional[str] = None
    info_additional: Optional[str] = None
    # Language
    language: Optional[str] = None
    # Source tracking
    source_url: Optional[str] = None
    source_trip_id: Optional[int] = None  # For translated circuits

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    items: List[TripSummaryResponse]
    total: int
    page: int
    page_size: int


# Endpoints
@router.get("", response_model=TripListResponse)
async def list_trips(
    db: DbSession,
    tenant: CurrentTenant,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    List trips for the current tenant.
    """
    query = select(Trip).where(Trip.tenant_id == tenant.id)

    # Filters
    if type:
        query = query.where(Trip.type == type)
    if status:
        query = query.where(Trip.status == status)
    if search:
        query = query.where(
            Trip.name.ilike(f"%{search}%") | Trip.client_name.ilike(f"%{search}%")
        )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Trip.updated_at.desc())

    # Eager-load days with their location relation for locations_summary
    query = query.options(
        selectinload(Trip.days).selectinload(TripDay.location),
    )

    result = await db.execute(query)
    trips = result.scalars().all()

    # Build summary with locations
    items = []
    for trip in trips:
        summary = TripSummaryResponse.model_validate(trip)
        # Extract unique location names from days
        locations: list[str] = []
        if trip.days:
            for day in sorted(trip.days, key=lambda d: d.sort_order or d.day_number):
                # Prefer location FK name, fallback to text fields
                name = None
                if day.location and day.location.name:
                    name = day.location.name
                elif day.location_from:
                    name = day.location_from
                if name and name not in locations:
                    locations.append(name)
                # Also check location_to
                if day.location_to and day.location_to not in locations:
                    locations.append(day.location_to)
        summary.locations_summary = locations[:8]  # Max 8 locations
        items.append(summary)

    return TripListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    data: TripCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new trip.
    If template_id is provided, copy structure from template.
    """
    trip = Trip(
        tenant_id=tenant.id,
        created_by_id=user.id,
        **data.model_dump(),
    )
    db.add(trip)
    await db.flush()

    # If deriving from template, copy structure
    if data.template_id:
        await _copy_trip_structure(db, tenant.id, data.template_id, trip.id)

    await db.commit()

    # Reload with relations
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip.id)
        .options(
            selectinload(Trip.days).selectinload(TripDay.formulas),
            selectinload(Trip.pax_configs),
        )
    )
    trip = result.scalar_one()

    return TripResponse.model_validate(trip)


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a trip with all its structure (days, formulas, items, pax configs).
    """
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(
            selectinload(Trip.days).selectinload(TripDay.formulas).selectinload(Formula.items),
            selectinload(Trip.pax_configs),
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    return TripResponse.model_validate(trip)


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: int,
    data: TripUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update trip metadata.
    """
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(
            selectinload(Trip.days),
            selectinload(Trip.pax_configs),
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(trip, field, value)

    await db.commit()
    await db.refresh(trip)

    return TripResponse.model_validate(trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a trip.
    """
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    await db.delete(trip)
    await db.commit()


@router.post("/{trip_id}/duplicate", response_model=TripResponse)
async def duplicate_trip(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    new_name: Optional[str] = None,
    as_type: Optional[str] = None,
):
    """
    Duplicate a trip with all its structure.
    """
    # Get source trip
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    source_trip = result.scalar_one_or_none()

    if not source_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Create new trip
    new_trip = Trip(
        tenant_id=tenant.id,
        name=new_name or f"{source_trip.name} (copie)",
        type=as_type or source_trip.type,
        template_id=source_trip.id if as_type == "client" else source_trip.template_id,
        duration_days=source_trip.duration_days,
        destination_country=source_trip.destination_country,
        default_currency=source_trip.default_currency,
        margin_pct=source_trip.margin_pct,
        margin_type=source_trip.margin_type,
        vat_pct=source_trip.vat_pct,
        operator_commission_pct=source_trip.operator_commission_pct,
        currency_rates_json=source_trip.currency_rates_json,
        status="draft",
        created_by_id=user.id,
    )
    db.add(new_trip)
    await db.flush()

    # Copy structure
    await _copy_trip_structure(db, tenant.id, trip_id, new_trip.id)

    await db.commit()

    # Reload
    result = await db.execute(
        select(Trip)
        .where(Trip.id == new_trip.id)
        .options(
            selectinload(Trip.days),
            selectinload(Trip.pax_configs),
        )
    )
    trip = result.scalar_one()

    return TripResponse.model_validate(trip)


async def _copy_trip_structure(
    db: DbSession,
    tenant_id: int,
    source_trip_id: int,
    target_trip_id: int,
):
    """
    Copy days, formulas, and items from source to target trip.
    """
    # Get source structure (eager load formulas with children and items)
    result = await db.execute(
        select(TripDay)
        .where(TripDay.trip_id == source_trip_id)
        .options(
            selectinload(TripDay.formulas).selectinload(Formula.items),
            selectinload(TripDay.formulas).selectinload(Formula.children).selectinload(Formula.items),
        )
    )
    source_days = result.scalars().all()

    # Get source pax configs
    result = await db.execute(
        select(TripPaxConfig).where(TripPaxConfig.trip_id == source_trip_id)
    )
    source_pax_configs = result.scalars().all()

    # Copy TripConditions (conditions are tenant-level → no need to copy them)
    result = await db.execute(
        select(TripCondition).where(TripCondition.trip_id == source_trip_id)
    )
    source_trip_conditions = result.scalars().all()
    for source_tc in source_trip_conditions:
        new_tc = TripCondition(
            tenant_id=tenant_id,
            trip_id=target_trip_id,
            condition_id=source_tc.condition_id,
            selected_option_id=source_tc.selected_option_id,
            is_active=source_tc.is_active,
        )
        db.add(new_tc)

    # Copy days with 2-pass formula copy (parents first, then children)
    for source_day in source_days:
        new_day = TripDay(
            tenant_id=tenant_id,
            trip_id=target_trip_id,
            day_number=source_day.day_number,
            day_number_end=source_day.day_number_end,
            title=source_day.title,
            description=source_day.description,
            location_from=source_day.location_from,
            location_to=source_day.location_to,
            location_id=source_day.location_id,
            sort_order=source_day.sort_order,
        )
        db.add(new_day)
        await db.flush()

        # Pass 1: Copy top-level blocks (parent_block_id is NULL)
        block_id_map = {}  # old_id -> new_id
        for source_formula in source_day.formulas:
            if source_formula.parent_block_id is not None:
                continue  # Skip children, handled in pass 2

            new_formula = Formula(
                tenant_id=tenant_id,
                trip_day_id=new_day.id,
                name=source_formula.name,
                description_html=source_formula.description_html,
                service_day_start=source_formula.service_day_start,
                service_day_end=source_formula.service_day_end,
                template_source_id=source_formula.id,
                sort_order=source_formula.sort_order,
                block_type=source_formula.block_type,
                parent_block_id=None,
                condition_id=source_formula.condition_id,
            )
            db.add(new_formula)
            await db.flush()
            block_id_map[source_formula.id] = new_formula.id

            # Copy items for this block
            for source_item in source_formula.items:
                new_item = Item(
                    tenant_id=tenant_id,
                    formula_id=new_formula.id,
                    name=source_item.name,
                    cost_nature_id=source_item.cost_nature_id,
                    supplier_id=source_item.supplier_id,
                    rate_catalog_id=source_item.rate_catalog_id,
                    contract_rate_id=source_item.contract_rate_id,
                    currency=source_item.currency,
                    unit_cost=source_item.unit_cost,
                    pricing_method=source_item.pricing_method,
                    pricing_value=source_item.pricing_value,
                    ratio_categories=source_item.ratio_categories,
                    ratio_per=source_item.ratio_per,
                    ratio_type=source_item.ratio_type,
                    times_type=source_item.times_type,
                    times_value=source_item.times_value,
                    condition_option_id=source_item.condition_option_id,
                    sort_order=source_item.sort_order,
                )
                db.add(new_item)

        # Pass 2: Copy children (parent_block_id is NOT NULL)
        for source_formula in source_day.formulas:
            if source_formula.parent_block_id is None:
                continue  # Already copied in pass 1

            new_parent_id = block_id_map.get(source_formula.parent_block_id)
            if not new_parent_id:
                continue  # Orphaned child, skip

            new_formula = Formula(
                tenant_id=tenant_id,
                trip_day_id=new_day.id,
                name=source_formula.name,
                description_html=source_formula.description_html,
                service_day_start=source_formula.service_day_start,
                service_day_end=source_formula.service_day_end,
                template_source_id=source_formula.id,
                sort_order=source_formula.sort_order,
                block_type=source_formula.block_type,
                parent_block_id=new_parent_id,
                condition_id=source_formula.condition_id,
            )
            db.add(new_formula)
            await db.flush()

            # Copy items for this sub-formula
            for source_item in source_formula.items:
                new_item = Item(
                    tenant_id=tenant_id,
                    formula_id=new_formula.id,
                    name=source_item.name,
                    cost_nature_id=source_item.cost_nature_id,
                    supplier_id=source_item.supplier_id,
                    rate_catalog_id=source_item.rate_catalog_id,
                    contract_rate_id=source_item.contract_rate_id,
                    currency=source_item.currency,
                    unit_cost=source_item.unit_cost,
                    pricing_method=source_item.pricing_method,
                    pricing_value=source_item.pricing_value,
                    ratio_categories=source_item.ratio_categories,
                    ratio_per=source_item.ratio_per,
                    ratio_type=source_item.ratio_type,
                    times_type=source_item.times_type,
                    times_value=source_item.times_value,
                    condition_option_id=source_item.condition_option_id,
                    sort_order=source_item.sort_order,
                )
                db.add(new_item)

    # Copy pax configs
    for source_config in source_pax_configs:
        new_config = TripPaxConfig(
            tenant_id=tenant_id,
            trip_id=target_trip_id,
            label=source_config.label,
            total_pax=source_config.total_pax,
            args_json=source_config.args_json,
            margin_override_pct=source_config.margin_override_pct,
        )
        db.add(new_config)


# ============================================================================
# TripDay CRUD
# ============================================================================

@router.post("/{trip_id}/days", response_model=TripDayResponse, status_code=201)
async def create_trip_day(
    trip_id: int,
    data: TripDayCreate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Create a new day for a trip."""
    # Verify trip belongs to tenant
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Calculate day_number if not provided
    if data.day_number is None:
        result = await db.execute(
            select(func.max(TripDay.day_number)).where(TripDay.trip_id == trip_id)
        )
        max_day = result.scalar() or 0
        day_number = max_day + 1
    else:
        day_number = data.day_number

    new_day = TripDay(
        tenant_id=tenant.id,
        trip_id=trip_id,
        day_number=day_number,
        day_number_end=data.day_number_end,
        title=data.title,
        description=data.description,
        location_from=data.location_from,
        location_to=data.location_to,
        location_id=data.location_id,
        sort_order=day_number,
    )
    db.add(new_day)
    await db.commit()
    await db.refresh(new_day)

    logger.info(f"Created day {day_number} for trip {trip_id}")
    return TripDayResponse.model_validate(new_day)


@router.patch("/{trip_id}/days/{day_id}", response_model=TripDayResponse)
async def update_trip_day(
    trip_id: int,
    day_id: int,
    data: TripDayUpdate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Update a trip day (title, description, multi-day range, etc.)."""
    # Fetch the day with trip ownership check
    result = await db.execute(
        select(TripDay).join(Trip).where(
            TripDay.id == day_id,
            TripDay.trip_id == trip_id,
            Trip.tenant_id == tenant.id,
        )
    )
    day = result.scalar_one_or_none()
    if not day:
        raise HTTPException(status_code=404, detail="Day not found")

    # Apply updates
    update_data = data.model_dump(exclude_unset=True)

    # Validate day_number_end if provided
    if "day_number_end" in update_data and update_data["day_number_end"] is not None:
        effective_day_number = update_data.get("day_number", day.day_number)
        if update_data["day_number_end"] <= effective_day_number:
            raise HTTPException(
                status_code=400,
                detail="day_number_end must be greater than day_number"
            )

    for field, value in update_data.items():
        setattr(day, field, value)

    await db.commit()
    await db.refresh(day)

    logger.info(f"Updated day {day_id} for trip {trip_id}: {list(update_data.keys())}")
    return TripDayResponse.model_validate(day)


class ExtendDayRequest(BaseModel):
    delta: int = Field(..., description="+1 to extend, -1 to shrink the day block")


@router.post("/{trip_id}/days/{day_id}/extend", response_model=List[TripDayResponse])
async def extend_trip_day(
    trip_id: int,
    day_id: int,
    data: ExtendDayRequest,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Extend or shrink a day block and renumber all subsequent days atomically."""
    # Fetch the target day
    result = await db.execute(
        select(TripDay).join(Trip).where(
            TripDay.id == day_id,
            TripDay.trip_id == trip_id,
            Trip.tenant_id == tenant.id,
        )
    )
    day = result.scalar_one_or_none()
    if not day:
        raise HTTPException(status_code=404, detail="Day not found")

    current_end = day.day_number_end or day.day_number
    new_end = current_end + data.delta

    # Cannot shrink below the start day
    if new_end < day.day_number:
        raise HTTPException(status_code=400, detail="Cannot shrink block below its start day")

    # Update the target day's end
    if new_end == day.day_number:
        day.day_number_end = None  # Single day — no end needed
    else:
        day.day_number_end = new_end

    # Fetch all days for this trip to renumber subsequent ones
    all_days_result = await db.execute(
        select(TripDay).where(TripDay.trip_id == trip_id).order_by(TripDay.day_number)
    )
    all_days = list(all_days_result.scalars().all())

    # Shift subsequent days by delta
    for d in all_days:
        if d.id != day.id and d.day_number > current_end:
            d.day_number += data.delta
            if d.day_number_end is not None:
                d.day_number_end += data.delta

    await db.commit()

    # Refresh and return all days
    refreshed = await db.execute(
        select(TripDay).where(TripDay.trip_id == trip_id).order_by(TripDay.day_number)
    )
    result_days = list(refreshed.scalars().all())
    logger.info(f"Extended day {day_id} for trip {trip_id}: delta={data.delta}, new_end={new_end}")
    return [TripDayResponse.model_validate(d) for d in result_days]


class ReorderDaysRequest(BaseModel):
    day_ids: List[int] = Field(..., description="Ordered list of day IDs in the desired new order")


@router.post("/{trip_id}/days/reorder", response_model=List[TripDayResponse])
async def reorder_trip_days(
    trip_id: int,
    data: ReorderDaysRequest,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Reorder trip days.
    Receives the list of day IDs in the desired visual order.
    Renumbers day_number (and day_number_end for multi-day blocks) sequentially.
    """
    # Verify trip belongs to tenant
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Fetch all days for this trip
    result = await db.execute(
        select(TripDay).where(TripDay.trip_id == trip_id)
    )
    all_days = {d.id: d for d in result.scalars().all()}

    # Validate that all IDs belong to this trip
    if set(data.day_ids) != set(all_days.keys()):
        raise HTTPException(
            status_code=400,
            detail="day_ids must contain exactly all day IDs for this trip"
        )

    # Renumber days sequentially based on the new order
    current_day_number = 1
    for day_id in data.day_ids:
        day = all_days[day_id]
        # Calculate the span of this day block
        old_span = (day.day_number_end or day.day_number) - day.day_number  # 0 for single day
        day.day_number = current_day_number
        day.day_number_end = (current_day_number + old_span) if old_span > 0 else None
        day.sort_order = current_day_number
        current_day_number += old_span + 1  # Next day starts after this block

    await db.commit()

    # Return reordered days
    refreshed = await db.execute(
        select(TripDay).where(TripDay.trip_id == trip_id).order_by(TripDay.day_number)
    )
    result_days = list(refreshed.scalars().all())
    logger.info(f"Reordered days for trip {trip_id}: {data.day_ids}")
    return [TripDayResponse.model_validate(d) for d in result_days]


@router.delete("/{trip_id}/days/{day_id}", status_code=204)
async def delete_trip_day(
    trip_id: int,
    day_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Delete a trip day."""
    result = await db.execute(
        select(TripDay).join(Trip).where(
            TripDay.id == day_id,
            TripDay.trip_id == trip_id,
            Trip.tenant_id == tenant.id,
        )
    )
    day = result.scalar_one_or_none()
    if not day:
        raise HTTPException(status_code=404, detail="Day not found")

    await db.delete(day)
    await db.commit()

    logger.info(f"Deleted day {day_id} from trip {trip_id}")


# ============================================================================
# Image Generation
# ============================================================================

class GenerateImagesRequest(BaseModel):
    days: Optional[List[int]] = Field(None, description="Day numbers to generate (None = all)")
    overwrite: bool = Field(False, description="Overwrite existing images")
    quality: str = Field("high", description="'high' (Imagen 3) or 'fast' (Imagen 3 Fast)")


class TripPhotoVariants(BaseModel):
    hero: Optional[str] = None
    large: Optional[str] = None
    medium: Optional[str] = None
    thumb: Optional[str] = None
    lqip: Optional[str] = None


class TripPhotoResponse(BaseModel):
    day: int
    location: Optional[str] = None
    filename: str
    url: str
    variants: TripPhotoVariants


class GenerateImagesResponse(BaseModel):
    generated: int
    skipped: int
    errors: List[str]
    images: List[TripPhotoResponse]


class TripPhotoListItem(BaseModel):
    id: int
    trip_id: int
    day_number: Optional[int] = None
    destination: Optional[str] = None
    attraction_type: Optional[str] = None
    attraction_slug: Optional[str] = None
    seo_filename: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    url_avif: Optional[str] = None
    url_webp: Optional[str] = None
    url_medium: Optional[str] = None
    url_large: Optional[str] = None
    url_hero: Optional[str] = None
    lqip_data_url: Optional[str] = None
    srcset_json: Optional[List[dict]] = None
    alt_text: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_hero: bool = False
    is_ai_generated: bool = False
    sort_order: int = 0
    ai_prompt: Optional[str] = None
    ai_model: Optional[str] = None

    class Config:
        from_attributes = True


class RegeneratePhotoRequest(BaseModel):
    prompt: Optional[str] = Field(None, description="Custom prompt (None = rebuild from day description)")
    negative_prompt: Optional[str] = Field(None, description="Custom negative prompt")
    quality: str = Field("high", description="'high' (Imagen 3) or 'fast' (Imagen 3 Fast)")


@router.post("/{trip_id}/generate-images", response_model=GenerateImagesResponse)
async def generate_trip_images(
    trip_id: int,
    data: GenerateImagesRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Generate AI images for a circuit's day-by-day descriptions.

    Uses Vertex AI (Imagen 3) to generate photos, then processes them into
    optimized variants (AVIF, WebP) with SEO-friendly nomenclature:
    Destination / Type / Attraction / seo-filename.avif

    This can take several minutes depending on the number of days.
    """
    # Verify trip exists and belongs to tenant
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Import the generator service
    from app.services.circuit_image_generator import generate_circuit_images

    # Run generation
    gen_result = await generate_circuit_images(
        db=db,
        trip_id=trip_id,
        tenant_id=str(tenant.id),
        days=data.days,
        overwrite=data.overwrite,
        quality=data.quality,
    )

    # Format response
    images_response = []
    for img in gen_result.images:
        images_response.append(TripPhotoResponse(
            day=img["day"],
            location=img.get("location"),
            filename=img["filename"],
            url=img["url"],
            variants=TripPhotoVariants(
                hero=img["variants"].get("hero"),
                large=img["variants"].get("large"),
                medium=img["variants"].get("medium"),
                thumb=img["variants"].get("thumb"),
                lqip=img["variants"].get("lqip"),
            ),
        ))

    return GenerateImagesResponse(
        generated=gen_result.generated,
        skipped=gen_result.skipped,
        errors=gen_result.errors,
        images=images_response,
    )


@router.get("/{trip_id}/photos", response_model=List[TripPhotoListItem])
async def list_trip_photos(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all photos for a trip, ordered by day number.
    """
    result = await db.execute(
        select(TripPhoto)
        .where(TripPhoto.trip_id == trip_id, TripPhoto.tenant_id == tenant.id)
        .order_by(TripPhoto.sort_order, TripPhoto.day_number)
    )
    photos = result.scalars().all()

    return [TripPhotoListItem.model_validate(p) for p in photos]


@router.post("/{trip_id}/photos/upload", response_model=TripPhotoListItem)
async def upload_trip_photo(
    trip_id: int,
    file: UploadFile = File(...),
    day_number: Optional[int] = Form(None),
    alt_text: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    destination: Optional[str] = Form(None),
    attraction_type: Optional[str] = Form(None),
    attraction_slug: Optional[str] = Form(None),
    seo_filename: Optional[str] = Form(None),
    is_hero: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Upload a manual photo for a trip with full optimization pipeline.

    Processes the image into 10 variants (5 sizes × AVIF + WebP) + LQIP,
    uploads all variants with SEO nomenclature, and creates a TripPhoto record.

    Same pipeline as AI-generated photos, but with is_ai_generated=False.
    """
    # 1. Verify trip belongs to tenant
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # 2. Read and validate file
    file_content = await file.read()
    file_size = len(file_content)
    mime_type = file.content_type or get_mime_type(file.filename or "image.jpg")

    is_valid, error_msg = validate_file(file_content, file.filename or "image.jpg", mime_type)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # 3. Resolve trip_day_id from day_number
    trip_day_id = None
    if day_number is not None:
        day_result = await db.execute(
            select(TripDay).where(
                TripDay.trip_id == trip_id,
                TripDay.day_number == day_number,
            )
        )
        trip_day = day_result.scalar_one_or_none()
        if trip_day:
            trip_day_id = trip_day.id

    # 4. Build SEO values with fallbacks
    country_code = trip.destination_country or ""
    effective_destination = destination or COUNTRY_DESTINATIONS.get(
        country_code.upper(), slugify(country_code or "unknown")
    )
    effective_attraction_type = attraction_type or "photo"

    original_name = (file.filename or "uploaded-image").rsplit(".", 1)[0]
    effective_attraction_slug = attraction_slug or slugify(original_name, max_length=40)
    effective_seo_filename = seo_filename or slugify(
        f"{original_name}-{effective_destination}", max_length=60
    )

    # 5. Run the FULL image processing pipeline (10 variants + LQIP)
    try:
        processing_result = process_image(file_content)
    except Exception as e:
        logger.exception(f"Failed to process image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process image: {e}",
        )

    # 6. Upload all variants with SEO nomenclature
    try:
        urls = {}
        srcset_entries = []

        for variant in processing_result.variants:
            variant_suffix = f"-{variant.size_name}"

            storage_path, public_url = await upload_seo_image(
                image_data=variant.data,
                tenant_id=str(tenant.id),
                destination=effective_destination,
                attraction_type=effective_attraction_type,
                attraction_slug=effective_attraction_slug,
                seo_filename=effective_seo_filename,
                variant_suffix=variant_suffix,
                file_format=variant.format,
                content_type=variant.content_type,
            )

            key = f"{variant.format}_{variant.size_name}"
            urls[key] = public_url

            srcset_entries.append({
                "url": public_url,
                "width": variant.width,
                "height": variant.height,
                "format": variant.format,
                "size": variant.size_name,
                "file_size": variant.file_size,
            })

        # 7. Upload master AVIF (original resolution)
        img = Image.open(io.BytesIO(file_content))
        master_avif = save_as_avif(img)
        master_path, master_url = await upload_seo_image(
            image_data=master_avif,
            tenant_id=str(tenant.id),
            destination=effective_destination,
            attraction_type=effective_attraction_type,
            attraction_slug=effective_attraction_slug,
            seo_filename=effective_seo_filename,
            variant_suffix="",
            file_format="avif",
            content_type="image/avif",
        )
    except Exception as e:
        logger.exception(f"Failed to upload image variants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image variants: {e}",
        )

    # 8. Calculate next sort_order
    sort_result = await db.execute(
        select(func.max(TripPhoto.sort_order))
        .where(TripPhoto.trip_id == trip_id, TripPhoto.tenant_id == tenant.id)
    )
    max_sort = sort_result.scalar_one_or_none()
    next_sort = (max_sort or 0) + 1

    # 9. If is_hero, unset existing hero photos
    if is_hero:
        await db.execute(
            sql_update(TripPhoto)
            .where(
                TripPhoto.trip_id == trip_id,
                TripPhoto.tenant_id == tenant.id,
                TripPhoto.is_hero == True,
            )
            .values(is_hero=False)
        )

    # 10. Create TripPhoto record
    photo = TripPhoto(
        tenant_id=tenant.id,
        trip_id=trip_id,
        trip_day_id=trip_day_id,
        day_number=day_number,
        destination=effective_destination,
        attraction_type=effective_attraction_type,
        attraction_slug=effective_attraction_slug,
        seo_filename=effective_seo_filename,
        storage_path=master_path,
        url=master_url,
        thumbnail_url=urls.get("webp_thumbnail") or urls.get("avif_thumbnail"),
        url_avif=urls.get("avif_medium") or urls.get("avif_large") or master_url,
        url_webp=urls.get("webp_medium") or urls.get("webp_large"),
        url_medium=urls.get("avif_medium") or urls.get("webp_medium"),
        url_large=urls.get("avif_large") or urls.get("webp_large"),
        url_hero=urls.get("avif_hero") or urls.get("avif_large") or master_url,
        srcset_json=srcset_entries,
        lqip_data_url=processing_result.lqip_data_url,
        original_filename=file.filename,
        file_size=file_size,
        mime_type=mime_type,
        width=processing_result.original_width,
        height=processing_result.original_height,
        alt_text=alt_text,
        caption_json={"default": caption} if caption else None,
        is_hero=is_hero,
        is_ai_generated=False,
        is_processed=True,
        sort_order=next_sort,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    logger.info(
        f"Manual photo uploaded for trip {trip_id}, day {day_number}: "
        f"{len(srcset_entries)} variants, master={master_url}"
    )

    return TripPhotoListItem.model_validate(photo)


@router.post("/{trip_id}/photos/{photo_id}/regenerate", response_model=TripPhotoListItem)
async def regenerate_trip_photo(
    trip_id: int,
    photo_id: int,
    data: RegeneratePhotoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Regenerate an existing trip photo with a new or edited prompt.

    The user can provide a custom prompt, or leave it empty to auto-rebuild
    the prompt from the day's title and description.
    Runs the full pipeline: Vertex AI → process_image → upload all variants.
    Updates the existing TripPhoto record in-place.
    """
    from datetime import timezone

    # Verify trip belongs to tenant
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.days))
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Fetch the photo
    result = await db.execute(
        select(TripPhoto).where(
            TripPhoto.id == photo_id,
            TripPhoto.trip_id == trip_id,
            TripPhoto.tenant_id == tenant.id,
        )
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Determine the prompt to use
    if data.prompt:
        # User provided a custom prompt
        prompt = data.prompt
        negative_prompt = data.negative_prompt or (
            "blurry, low quality, distorted, ugly, watermark, text, logo, "
            "fictional place, imaginary location, AI artifacts, unrealistic colors"
        )
    else:
        # Rebuild prompt from day description
        day = None
        if photo.day_number:
            day = next((d for d in trip.days if d.day_number == photo.day_number), None)

        if day:
            destination_name = COUNTRY_DESTINATIONS.get(trip.destination_country, trip.destination_country or "unknown")
            prompt, negative_prompt = build_prompt(
                location=day.title or f"Day {day.day_number}",
                destination_name=destination_name,
                scene_type="attraction",
                style="photorealistic",
                time_of_day="golden hour",
                day_title=day.title,
                day_description=day.description,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="No prompt provided and no day description available to rebuild one"
            )

    # Initialize Vertex AI image generation service
    from app.services.vertex_ai import ImageGenerationService
    if data.quality == "fast":
        image_service = get_image_generation_service()
        image_service = ImageGenerationService(model_name=ImageGenerationService.MODEL_IMAGEN_3_FAST)
    else:
        image_service = get_image_generation_service()

    # Generate image via Vertex AI
    logger.info(f"Regenerating photo {photo_id} for trip {trip_id} with prompt: {prompt[:100]}...")
    images = await image_service.generate_image(
        prompt=prompt,
        negative_prompt=negative_prompt,
        number_of_images=1,
        aspect_ratio="16:9",
        guidance_scale=8.0,
    )

    if not images:
        raise HTTPException(status_code=500, detail="Image generation failed - no image returned")

    raw_bytes = image_service.get_image_bytes(images[0])

    # Process image → generate all variants (AVIF, WebP × 5 sizes + LQIP)
    processing_result = process_image(raw_bytes)

    # Use existing SEO metadata from the photo, or build defaults
    destination = photo.destination or COUNTRY_DESTINATIONS.get(
        trip.destination_country, "unknown"
    )
    attraction_type = photo.attraction_type or "attraction"
    attraction_slug = photo.attraction_slug or slugify(
        photo.seo_filename or f"photo-{photo.day_number or 0}", max_length=40
    )
    seo_filename = photo.seo_filename or slugify(
        f"{attraction_slug}-{destination}", max_length=60
    )

    # Upload all variants with SEO nomenclature
    urls = {}
    srcset_entries = []

    for variant in processing_result.variants:
        variant_suffix = f"-{variant.size_name}"
        file_format = variant.format

        storage_path, public_url = await upload_seo_image(
            image_data=variant.data,
            tenant_id=str(tenant.id),
            destination=destination,
            attraction_type=attraction_type,
            attraction_slug=attraction_slug,
            seo_filename=seo_filename,
            variant_suffix=variant_suffix,
            file_format=file_format,
            content_type=variant.content_type,
        )

        key = f"{variant.format}_{variant.size_name}"
        urls[key] = public_url

        srcset_entries.append({
            "url": public_url,
            "width": variant.width,
            "height": variant.height,
            "format": variant.format,
            "size": variant.size_name,
            "file_size": variant.file_size,
        })

    # Upload master AVIF
    img = Image.open(io.BytesIO(raw_bytes))
    master_avif = save_as_avif(img)
    master_path, master_url = await upload_seo_image(
        image_data=master_avif,
        tenant_id=str(tenant.id),
        destination=destination,
        attraction_type=attraction_type,
        attraction_slug=attraction_slug,
        seo_filename=seo_filename,
        variant_suffix="",
        file_format="avif",
        content_type="image/avif",
    )

    # Update the existing photo record
    photo.storage_path = master_path
    photo.url = master_url
    photo.url_avif = urls.get("avif_medium") or urls.get("avif_large") or master_url
    photo.url_webp = urls.get("webp_medium") or urls.get("webp_large")
    photo.url_medium = urls.get("avif_medium") or urls.get("webp_medium")
    photo.url_large = urls.get("avif_large") or urls.get("webp_large")
    photo.url_hero = urls.get("avif_hero") or urls.get("avif_large") or master_url
    photo.thumbnail_url = urls.get("webp_thumbnail") or urls.get("avif_thumbnail")
    photo.srcset_json = srcset_entries
    photo.lqip_data_url = processing_result.lqip_data_url
    photo.width = processing_result.original_width
    photo.height = processing_result.original_height
    photo.ai_prompt = prompt
    photo.ai_negative_prompt = negative_prompt
    photo.ai_model = image_service.model_name
    photo.ai_generated_at = datetime.now(timezone.utc)
    photo.is_ai_generated = True
    photo.is_processed = True

    await db.commit()
    await db.refresh(photo)

    logger.info(
        f"Photo {photo_id} regenerated for trip {trip_id}: "
        f"{len(srcset_entries)} variants, master={master_url}"
    )

    return TripPhotoListItem.model_validate(photo)
