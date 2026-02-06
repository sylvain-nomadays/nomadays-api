"""
Trip/Circuit management endpoints.
"""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import Trip, TripDay, TripPaxConfig
from app.models.formula import Formula
from app.models.item import Item

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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TripDayResponse(BaseModel):
    id: int
    day_number: int
    title: Optional[str]
    description: Optional[str]
    location_from: Optional[str]
    location_to: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


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

    result = await db.execute(query)
    trips = result.scalars().all()

    return TripListResponse(
        items=[TripSummaryResponse.model_validate(t) for t in trips],
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
    # Get source structure
    result = await db.execute(
        select(TripDay)
        .where(TripDay.trip_id == source_trip_id)
        .options(selectinload(TripDay.formulas).selectinload(Formula.items))
    )
    source_days = result.scalars().all()

    # Get source pax configs
    result = await db.execute(
        select(TripPaxConfig).where(TripPaxConfig.trip_id == source_trip_id)
    )
    source_pax_configs = result.scalars().all()

    # Copy days
    for source_day in source_days:
        new_day = TripDay(
            tenant_id=tenant_id,
            trip_id=target_trip_id,
            day_number=source_day.day_number,
            title=source_day.title,
            description=source_day.description,
            location_from=source_day.location_from,
            location_to=source_day.location_to,
            sort_order=source_day.sort_order,
        )
        db.add(new_day)
        await db.flush()

        # Copy formulas
        for source_formula in source_day.formulas:
            new_formula = Formula(
                tenant_id=tenant_id,
                trip_day_id=new_day.id,
                name=source_formula.name,
                description_html=source_formula.description_html,
                service_day_start=source_formula.service_day_start,
                service_day_end=source_formula.service_day_end,
                template_source_id=source_formula.id,
                sort_order=source_formula.sort_order,
            )
            db.add(new_formula)
            await db.flush()

            # Copy items
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
