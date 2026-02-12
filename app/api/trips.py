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
from sqlalchemy import select, func, update as sql_update, text as sa_text, String as SAString
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
from app.models.cotation import TripCotation
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
    room_demand_json: Optional[list] = None


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
    vat_calculation_mode: Optional[str] = None
    operator_commission_pct: Optional[float] = None
    # Commissions
    primary_commission_pct: Optional[float] = None
    primary_commission_label: Optional[str] = None
    secondary_commission_pct: Optional[float] = None
    secondary_commission_label: Optional[str] = None
    # Characteristics
    comfort_level: Optional[int] = None
    difficulty_level: Optional[int] = None
    # Exchange rates
    currency_rates_json: Optional[dict] = None
    room_demand_json: Optional[list] = None
    status: Optional[str] = None
    # Themes
    theme_ids: Optional[List[int]] = None
    # Presentation fields
    description_short: Optional[str] = None
    description_html: Optional[str] = None
    description_tone: Optional[str] = None
    slug: Optional[str] = None
    highlights: Optional[List[dict]] = None
    inclusions: Optional[List[dict]] = None
    exclusions: Optional[List[dict]] = None
    info_general: Optional[str] = None
    info_formalities: Optional[str] = None
    info_booking_conditions: Optional[str] = None
    info_cancellation_policy: Optional[str] = None
    info_additional: Optional[str] = None
    # Rich text HTML versions
    info_general_html: Optional[str] = None
    info_formalities_html: Optional[str] = None
    info_booking_conditions_html: Optional[str] = None
    info_cancellation_policy_html: Optional[str] = None
    info_additional_html: Optional[str] = None
    # Roadbook
    roadbook_intro_html: Optional[str] = None
    # Language for translation
    language: Optional[str] = None


class CotationSummary(BaseModel):
    """Lightweight cotation summary for list views."""
    id: int
    name: str
    mode: str  # "range" or "custom"
    tarification_mode: Optional[str] = None  # "range_web", "per_person", etc.
    price_label: Optional[str] = None  # e.g. "1 250 €/pers" or "4 500 € / groupe"


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
    # Enriched fields for dossier view
    hero_photo_url: Optional[str] = None
    cotations_summary: List[CotationSummary] = []
    sent_at: Optional[datetime] = None
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
    room_demand_json: Optional[list] = None
    # Commissions
    primary_commission_pct: Optional[float] = None
    primary_commission_label: Optional[str] = None
    secondary_commission_pct: Optional[float] = None
    secondary_commission_label: Optional[str] = None
    vat_calculation_mode: Optional[str] = None
    exchange_rate_mode: Optional[str] = None
    # Characteristics
    comfort_level: Optional[int] = None
    difficulty_level: Optional[int] = None
    # Dossier
    dossier_id: Optional[UUID] = None
    # Multi-destination
    destination_countries: Optional[List[str]] = None
    status: str
    version: int
    days: List[TripDayResponse] = []
    pax_configs: List[TripPaxConfigResponse] = []
    formulas: List[dict] = []
    # Presentation fields
    description_short: Optional[str] = None
    description_html: Optional[str] = None
    description_tone: Optional[str] = None
    slug: Optional[str] = None
    highlights: Optional[List[dict]] = None
    inclusions: Optional[List[dict]] = None
    exclusions: Optional[List[dict]] = None
    info_general: Optional[str] = None
    info_formalities: Optional[str] = None
    info_booking_conditions: Optional[str] = None
    info_cancellation_policy: Optional[str] = None
    info_additional: Optional[str] = None
    # Rich text HTML versions
    info_general_html: Optional[str] = None
    info_formalities_html: Optional[str] = None
    info_booking_conditions_html: Optional[str] = None
    info_cancellation_policy_html: Optional[str] = None
    info_additional_html: Optional[str] = None
    # Roadbook
    roadbook_intro_html: Optional[str] = None
    # Language
    language: Optional[str] = None
    # Source tracking
    source_url: Optional[str] = None
    source_trip_id: Optional[int] = None  # For translated circuits
    # Publication
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    items: List[TripSummaryResponse]
    total: int
    page: int
    page_size: int


# Helpers

CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "THB": "฿", "VND": "₫", "GBP": "£", "CHF": "CHF"}


def _build_price_label(
    tarif_mode: Optional[str],
    entries: list,
    currency: str = "EUR",
) -> Optional[str]:
    """Build a human-readable price label from tarification entries."""
    if not tarif_mode or not entries:
        return None

    sym = CURRENCY_SYMBOLS.get(currency, currency)

    try:
        if tarif_mode == "range_web":
            # Show the range: "1 250 - 1 550 €/pers" or single "1 250 €/pers"
            prices = [e.get("selling_price", 0) for e in entries if e.get("selling_price")]
            if not prices:
                return None
            min_p = min(prices)
            max_p = max(prices)
            if min_p == max_p:
                return f"{int(min_p):,} {sym}/pers".replace(",", " ")
            return f"{int(min_p):,} - {int(max_p):,} {sym}/pers".replace(",", " ")

        elif tarif_mode == "per_person":
            # "1 250 €/pers"
            entry = entries[0] if entries else {}
            pp = entry.get("price_per_person") or entry.get("selling_price", 0)
            if not pp:
                return None
            return f"{int(pp):,} {sym}/pers".replace(",", " ")

        elif tarif_mode == "per_group":
            # "4 500 € / groupe"
            entry = entries[0] if entries else {}
            gp = entry.get("group_price") or entry.get("selling_price", 0)
            if not gp:
                return None
            return f"{int(gp):,} {sym} / groupe".replace(",", " ")

        elif tarif_mode in ("service_list", "enumeration"):
            # Sum of all entries selling prices
            total = sum(e.get("selling_price", 0) for e in entries)
            if not total:
                return None
            return f"{int(total):,} {sym}".replace(",", " ")

    except (ValueError, TypeError):
        return None

    return None


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
    dossier_id: Optional[str] = None,
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
    if dossier_id:
        query = query.where(Trip.dossier_id == dossier_id)
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

    # Eager-load days (locations), photos (hero only), cotations (tarification)
    query = query.options(
        selectinload(Trip.days).selectinload(TripDay.location),
        selectinload(Trip.photos),
        selectinload(Trip.cotations),
    )

    result = await db.execute(query)
    trips = result.scalars().all()

    # Build summary with locations, hero photo, and cotations
    items = []
    for trip in trips:
        summary = TripSummaryResponse.model_validate(trip)

        # Extract unique location names from days
        locations: list[str] = []
        if trip.days:
            for day in sorted(trip.days, key=lambda d: d.sort_order or d.day_number):
                name = None
                if day.location and day.location.name:
                    name = day.location.name
                elif day.location_from:
                    name = day.location_from
                if name and name not in locations:
                    locations.append(name)
                if day.location_to and day.location_to not in locations:
                    locations.append(day.location_to)
        summary.locations_summary = locations[:8]

        # Hero photo: pick the is_hero photo, prefer url_medium for thumbnail
        if trip.photos:
            hero = next((p for p in trip.photos if p.is_hero), None)
            if not hero:
                # Fallback to first photo
                hero = trip.photos[0] if trip.photos else None
            if hero:
                summary.hero_photo_url = hero.url_medium or hero.url_large or hero.url or None

        # Cotations summary: extract name + tarification mode + price label
        if trip.cotations:
            cot_summaries = []
            for cot in sorted(trip.cotations, key=lambda c: c.sort_order or 0):
                tarif = cot.tarification_json or {}
                tarif_mode = tarif.get("mode") if tarif else None
                price_label = _build_price_label(tarif_mode, tarif.get("entries", []), trip.default_currency)
                cot_summaries.append(CotationSummary(
                    id=cot.id,
                    name=cot.name,
                    mode=cot.mode,
                    tarification_mode=tarif_mode,
                    price_label=price_label,
                ))
            summary.cotations_summary = cot_summaries

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
            selectinload(Trip.themes),
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Handle theme_ids separately (M2M relationship)
    theme_ids = update_data.pop("theme_ids", None)
    if theme_ids is not None:
        from app.models.travel_theme import TravelTheme
        theme_result = await db.execute(
            select(TravelTheme).where(TravelTheme.id.in_(theme_ids))
        )
        trip.themes = list(theme_result.scalars().all())

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
    dossier_id: Optional[str] = None,
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

    # Fetch dossier data if linking to a dossier (for dates, pax, duration)
    dossier = None
    if dossier_id:
        from app.models.dossier import Dossier
        dossier_result = await db.execute(
            select(Dossier).where(
                Dossier.id == dossier_id,
                Dossier.tenant_id == tenant.id,
            )
        )
        dossier = dossier_result.scalar_one_or_none()

    # Compute dates and duration from dossier if available
    effective_start = (dossier.departure_date_from if dossier else None) or source_trip.start_date
    effective_end = (dossier.departure_date_to if dossier else None) or source_trip.end_date

    if dossier and dossier.departure_date_from and dossier.departure_date_to:
        effective_duration = (dossier.departure_date_to - dossier.departure_date_from).days + 1
    else:
        effective_duration = source_trip.duration_days

    # Create new trip with ALL fields (including presentation)
    new_trip = Trip(
        tenant_id=tenant.id,
        name=new_name or f"{source_trip.name} (copie)",
        type=as_type or source_trip.type,
        template_id=source_trip.id if as_type == "client" else source_trip.template_id,
        dossier_id=dossier_id or source_trip.dossier_id,
        # Dates & duration (from dossier if available)
        start_date=effective_start,
        end_date=effective_end,
        duration_days=effective_duration,
        # Core fields
        destination_country=source_trip.destination_country,
        destination_countries=source_trip.destination_countries,
        default_currency=source_trip.default_currency,
        margin_pct=source_trip.margin_pct,
        margin_type=source_trip.margin_type,
        vat_pct=source_trip.vat_pct,
        operator_commission_pct=source_trip.operator_commission_pct,
        currency_rates_json=source_trip.currency_rates_json,
        roadbook_intro_html=source_trip.roadbook_intro_html,
        # Presentation fields
        description_short=source_trip.description_short,
        description_html=source_trip.description_html,
        description_tone=source_trip.description_tone,
        highlights=source_trip.highlights,
        inclusions=source_trip.inclusions,
        exclusions=source_trip.exclusions,
        info_general=source_trip.info_general,
        info_formalities=source_trip.info_formalities,
        info_booking_conditions=source_trip.info_booking_conditions,
        info_cancellation_policy=source_trip.info_cancellation_policy,
        info_additional=source_trip.info_additional,
        info_general_html=source_trip.info_general_html,
        info_formalities_html=source_trip.info_formalities_html,
        info_booking_conditions_html=source_trip.info_booking_conditions_html,
        info_cancellation_policy_html=source_trip.info_cancellation_policy_html,
        info_additional_html=source_trip.info_additional_html,
        comfort_level=source_trip.comfort_level,
        difficulty_level=source_trip.difficulty_level,
        map_config=source_trip.map_config,
        # Commission & TVA
        primary_commission_pct=source_trip.primary_commission_pct,
        primary_commission_label=source_trip.primary_commission_label,
        secondary_commission_pct=source_trip.secondary_commission_pct,
        secondary_commission_label=source_trip.secondary_commission_label,
        vat_calculation_mode=source_trip.vat_calculation_mode,
        room_demand_json=source_trip.room_demand_json,
        exchange_rate_mode=source_trip.exchange_rate_mode,
        language=source_trip.language,
        # Do NOT copy: slug (unique), is_distributable, distribution_channels, source_url
        status="draft",
        created_by_id=user.id,
    )
    db.add(new_trip)
    await db.flush()

    # Copy structure (pass dossier for pax config generation)
    await _copy_trip_structure(db, tenant.id, trip_id, new_trip.id, dossier=dossier)

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
    dossier=None,
):
    """
    Copy days, formulas, items, photos, and pax configs from source to target trip.
    If dossier is provided, generate pax configs from dossier composition instead of copying source.
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
    day_id_map = {}  # source_day_id -> new_day_id (used for photo copy)
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
            roadbook_html=source_day.roadbook_html,
        )
        db.add(new_day)
        await db.flush()
        day_id_map[source_day.id] = new_day.id

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

    # Copy or generate pax configs
    if dossier and (dossier.pax_adults or dossier.pax_children):
        # Generate pax config from dossier composition
        from app.services.pax_generator import generate_custom_config
        configs = generate_custom_config(
            adult=dossier.pax_adults or 0,
            child=dossier.pax_children or 0,
            baby=dossier.pax_infants or 0,
        )
        for config in configs:
            db.add(TripPaxConfig(
                tenant_id=tenant_id,
                trip_id=target_trip_id,
                label=config["label"],
                total_pax=config["total_pax"],
                args_json=config,
            ))
    else:
        # Copy source pax configs as-is
        for source_config in source_pax_configs:
            db.add(TripPaxConfig(
                tenant_id=tenant_id,
                trip_id=target_trip_id,
                label=source_config.label,
                total_pax=source_config.total_pax,
                args_json=source_config.args_json,
                margin_override_pct=source_config.margin_override_pct,
            ))

    # Copy photos (reuse same storage URLs, no re-upload)
    result = await db.execute(
        select(TripPhoto).where(TripPhoto.trip_id == source_trip_id)
        .order_by(TripPhoto.sort_order)
    )
    source_photos = result.scalars().all()
    for photo in source_photos:
        new_photo = TripPhoto(
            tenant_id=tenant_id,
            trip_id=target_trip_id,
            trip_day_id=day_id_map.get(photo.trip_day_id) if photo.trip_day_id else None,
            day_number=photo.day_number,
            storage_path=photo.storage_path,
            url=photo.url,
            thumbnail_url=photo.thumbnail_url,
            url_avif=getattr(photo, 'url_avif', None),
            url_webp=getattr(photo, 'url_webp', None),
            url_medium=getattr(photo, 'url_medium', None),
            url_large=getattr(photo, 'url_large', None),
            url_hero=getattr(photo, 'url_hero', None),
            srcset_json=getattr(photo, 'srcset_json', None),
            lqip_data_url=getattr(photo, 'lqip_data_url', None),
            alt_text=photo.alt_text,
            alt_text_json=getattr(photo, 'alt_text_json', None),
            caption_json=getattr(photo, 'caption_json', None),
            is_hero=photo.is_hero,
            is_ai_generated=photo.is_ai_generated,
            is_processed=photo.is_processed,
            sort_order=photo.sort_order,
            original_filename=photo.original_filename,
            file_size=photo.file_size,
            mime_type=photo.mime_type,
            width=photo.width,
            height=photo.height,
        )
        db.add(new_photo)


# ============================================================================
# Helper: auto-sync trip duration from day blocks
# ============================================================================

async def _sync_trip_duration(db: DbSession, trip_id: int):
    """Recalculate trip.duration_days from its TripDay blocks."""
    result = await db.execute(
        select(func.max(func.coalesce(TripDay.day_number_end, TripDay.day_number)))
        .where(TripDay.trip_id == trip_id)
    )
    max_day = result.scalar() or 1
    await db.execute(
        sql_update(Trip).where(Trip.id == trip_id).values(duration_days=max_day)
    )


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
    await db.flush()
    await _sync_trip_duration(db, trip_id)
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

    # Sync duration if day_number or day_number_end changed
    if "day_number" in update_data or "day_number_end" in update_data:
        await db.flush()
        await _sync_trip_duration(db, trip_id)

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

    await db.flush()
    await _sync_trip_duration(db, trip_id)
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

    await db.flush()
    await _sync_trip_duration(db, trip_id)
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
    await db.flush()
    await _sync_trip_duration(db, trip_id)
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


# ============ TEMPLATE SYNC STATUS ============


class TemplateSyncItem(BaseModel):
    formula_id: int
    formula_name: str
    block_type: str
    day_number: Optional[int] = None
    template_source_id: int
    source_version: Optional[int] = None
    template_version: int = 1
    status: str  # 'in_sync' | 'template_updated'


class TripTemplateSyncResponse(BaseModel):
    trip_id: int
    total_linked: int = 0
    out_of_sync: int = 0
    items: List[TemplateSyncItem] = []


@router.get("/{trip_id}/template-sync-status", response_model=TripTemplateSyncResponse)
async def get_trip_template_sync_status(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Get template sync status for all template-linked blocks in a trip.

    Returns a list of all formulas that have a template_source_id, with
    their sync status (in_sync vs template_updated).
    """
    # Verify trip exists
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Find all formulas in this trip that are linked to templates
    from app.models.formula import Formula as FormulaModel

    result = await db.execute(
        select(FormulaModel, TripDay.day_number)
        .outerjoin(TripDay, FormulaModel.trip_day_id == TripDay.id)
        .where(
            TripDay.trip_id == trip_id,
            FormulaModel.tenant_id == tenant.id,
            FormulaModel.template_source_id.is_not(None),
            FormulaModel.is_template == False,  # noqa: E712
        )
    )
    linked_formulas = result.all()

    if not linked_formulas:
        return TripTemplateSyncResponse(trip_id=trip_id)

    # Get template versions in batch
    template_ids = list({f.template_source_id for f, _ in linked_formulas})
    result = await db.execute(
        select(FormulaModel.id, FormulaModel.template_version)
        .where(FormulaModel.id.in_(template_ids))
    )
    template_versions = {row.id: row.template_version for row in result.all()}

    items = []
    out_of_sync = 0
    for formula, day_number in linked_formulas:
        t_version = template_versions.get(formula.template_source_id, 1)
        source_version = formula.template_source_version or 0
        sync_status = "in_sync" if source_version >= t_version else "template_updated"
        if sync_status == "template_updated":
            out_of_sync += 1

        items.append(TemplateSyncItem(
            formula_id=formula.id,
            formula_name=formula.name,
            block_type=formula.block_type,
            day_number=day_number,
            template_source_id=formula.template_source_id,
            source_version=source_version,
            template_version=t_version,
            status=sync_status,
        ))

    return TripTemplateSyncResponse(
        trip_id=trip_id,
        total_linked=len(items),
        out_of_sync=out_of_sync,
        items=items,
    )


# =============================================================================
# Pre-booking: bookable items + request pre-bookings
# =============================================================================

class BookableItem(BaseModel):
    item_id: int
    item_name: str
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_email: Optional[str] = None
    block_type: Optional[str] = None
    formula_name: Optional[str] = None
    formula_id: Optional[int] = None
    day_number: Optional[int] = None
    service_date_start: Optional[date] = None
    service_date_end: Optional[date] = None
    requires_pre_booking: bool = False
    already_booked: bool = False
    booking_status: Optional[str] = None  # pending, sent, confirmed, modified, cancelled
    booking_requested_at: Optional[datetime] = None
    booking_requested_by: Optional[str] = None
    booking_days_waiting: Optional[int] = None  # Days since request was made
    booking_overdue: bool = False  # True if waiting > 2 business days


class PreBookingRequest(BaseModel):
    item_ids: List[int]
    pax_count: Optional[int] = None
    guest_names: Optional[str] = None
    notes: Optional[str] = None


class PreBookingCreated(BaseModel):
    booking_id: int
    item_name: str
    supplier_name: Optional[str] = None
    status: str


@router.get("/{trip_id}/bookable-items", response_model=List[BookableItem])
async def get_bookable_items(
    trip_id: int,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    List items in a circuit that can be pre-booked.
    Includes all items linked to a supplier (with supplier.requires_pre_booking flag).
    """
    from app.models.supplier import Supplier
    from app.models.booking import Booking

    # Verify trip belongs to tenant
    trip = await db.get(Trip, trip_id)
    if not trip or trip.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Circuit non trouvé")

    # Load all items with suppliers, via formulas -> trip_days
    result = await db.execute(
        select(Item, Formula, TripDay)
        .join(Formula, Item.formula_id == Formula.id)
        .join(TripDay, Formula.trip_day_id == TripDay.id)
        .outerjoin(Supplier, Item.supplier_id == Supplier.id)
        .where(TripDay.trip_id == trip_id)
        .where(Item.supplier_id.isnot(None))
        .options(
            selectinload(Item.supplier),
        )
        .order_by(TripDay.day_number, Formula.sort_order, Item.sort_order)
    )
    rows = result.all()

    # Check which items already have a pre-booking (with status, date, requester)
    existing_bookings = await db.execute(
        select(
            Booking.item_id,
            Booking.status,
            Booking.created_at,
            User.first_name,
            User.last_name,
        )
        .outerjoin(User, Booking.requested_by_id == User.id)
        .where(Booking.trip_id == trip_id)
        .where(Booking.is_pre_booking.is_(True))
        .where(sa_text("bookings.status != 'cancelled'"))
    )
    # Map item_id -> booking info
    booked_item_info: dict[int, dict] = {}
    for row in existing_bookings.all():
        if row[0]:
            requester_name = None
            if row[3] or row[4]:
                requester_name = f"{row[3] or ''} {row[4] or ''}".strip()
            booked_item_info[row[0]] = {
                "status": row[1],
                "created_at": row[2],
                "requested_by": requester_name,
            }

    from datetime import timedelta

    items_out = []
    for item, formula, trip_day in rows:
        supplier = item.supplier
        # Calculate service dates from trip_day.day_number (absolute day in circuit)
        sds = None
        sde = None
        if trip.start_date and trip_day and trip_day.day_number:
            sds = trip.start_date + timedelta(days=(trip_day.day_number - 1))
            nights = 0
            if formula and formula.service_day_end and formula.service_day_start:
                nights = formula.service_day_end - formula.service_day_start
            sde = sds + timedelta(days=max(nights, 0))

        booking_info = booked_item_info.get(item.id)

        # Calculate waiting time and overdue status
        days_waiting = None
        is_overdue = False
        if booking_info and booking_info["created_at"] and booking_info["status"] == "pending":
            from datetime import timezone
            created = booking_info["created_at"]
            if created.tzinfo:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.utcnow()
            days_waiting = (now - created).days
            # Overdue if > 2 business days (~3 calendar days to account for weekends)
            is_overdue = days_waiting >= 3

        items_out.append(BookableItem(
            item_id=item.id,
            item_name=item.name,
            supplier_id=supplier.id if supplier else None,
            supplier_name=supplier.name if supplier else None,
            supplier_email=supplier.reservation_email if supplier else None,
            block_type=formula.block_type,
            formula_name=formula.name,
            formula_id=formula.id,
            day_number=trip_day.day_number,
            service_date_start=sds,
            service_date_end=sde,
            requires_pre_booking=getattr(supplier, 'requires_pre_booking', False) if supplier else False,
            already_booked=booking_info is not None,
            booking_status=booking_info["status"] if booking_info else None,
            booking_requested_at=booking_info["created_at"] if booking_info else None,
            booking_requested_by=booking_info["requested_by"] if booking_info else None,
            booking_days_waiting=days_waiting,
            booking_overdue=is_overdue,
        ))

    return items_out


@router.post("/{trip_id}/request-pre-bookings", response_model=List[PreBookingCreated])
async def request_pre_bookings(
    trip_id: int,
    body: PreBookingRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Create pre-booking requests for selected items in a circuit.
    Notifies the logistics team.
    """
    from app.models.supplier import Supplier
    from app.models.booking import Booking
    from app.services.notification_service import notify_logistics_team

    # Verify trip
    trip = await db.get(Trip, trip_id)
    if not trip or trip.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Circuit non trouvé")

    if not body.item_ids:
        raise HTTPException(status_code=400, detail="Aucun item sélectionné")

    # Load items with suppliers, formulas, AND trip_days (for correct date calc)
    from datetime import timedelta

    result = await db.execute(
        select(Item, Formula, TripDay)
        .join(Formula, Item.formula_id == Formula.id)
        .join(TripDay, Formula.trip_day_id == TripDay.id)
        .where(Item.id.in_(body.item_ids))
        .options(
            selectinload(Item.supplier),
            selectinload(Item.cost_nature),
        )
    )
    rows = result.all()

    created_bookings = []
    for item, formula, trip_day in rows:
        supplier = item.supplier

        # Calculate service dates from trip_day.day_number (absolute day in circuit)
        sds = date.today()
        sde = date.today()
        if trip.start_date and trip_day and trip_day.day_number:
            sds = trip.start_date + timedelta(days=(trip_day.day_number - 1))
            # Multi-night: end = start + (service_day_end - service_day_start)
            nights = 0
            if formula and formula.service_day_end and formula.service_day_start:
                nights = formula.service_day_end - formula.service_day_start
            sde = sds + timedelta(days=max(nights, 0))

        booking = Booking(
            tenant_id=tenant.id,
            trip_id=trip_id,
            item_id=item.id,
            supplier_id=supplier.id if supplier else None,
            cost_nature_id=item.cost_nature_id or 1,  # Default to 1 if not set
            description=f"{formula.name if formula else ''} — {item.name}",
            service_date_start=sds,
            service_date_end=sde,
            booked_amount=item.unit_cost or 0,
            currency=item.currency or "EUR",
            vat_recoverable=False,
            status="pending",
            is_pre_booking=True,
            requested_by_id=user.id,
            formula_id=formula.id if formula else None,
            pax_count=body.pax_count,
            guest_names=body.guest_names,
            supplier_response_note=body.notes,
        )
        db.add(booking)
        created_bookings.append((booking, item, supplier))

    await db.flush()

    # Notify logistics team
    try:
        await notify_logistics_team(
            db=db,
            tenant_id=tenant.id,
            type="pre_booking_request",
            title=f"Nouvelle demande de pré-réservation — {trip.name}",
            message=f"{len(created_bookings)} service(s) à réserver pour le circuit {trip.name}",
            link=f"/admin/reservations?trip_id={trip_id}",
            metadata={"trip_id": trip_id, "trip_name": trip.name, "count": len(created_bookings)},
        )
    except Exception as e:
        logger.warning(f"Failed to send notifications: {e}")
        # Rollback the failed notification flush, then re-flush bookings
        await db.rollback()
        # Re-add bookings to a fresh transaction
        for booking, _, _ in created_bookings:
            db.add(booking)
        await db.flush()

    await db.commit()

    return [
        PreBookingCreated(
            booking_id=b.id,
            item_name=item.name,
            supplier_name=s.name if s else None,
            status=b.status,
        )
        for b, item, s in created_bookings
    ]


# =============================================================================
# Publish trip (draft → sent) + email to client
# =============================================================================

class PublishTripRequest(BaseModel):
    client_email: Optional[str] = None  # Override dossier client email
    send_email: bool = True  # Whether to send the email (default: yes)


class PublishTripResponse(BaseModel):
    trip: TripSummaryResponse
    email_sent: bool


@router.post("/{trip_id}/publish", response_model=PublishTripResponse)
async def publish_trip(
    trip_id: int,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
    body: Optional[PublishTripRequest] = None,
):
    """
    Publish a trip proposal: update status to 'sent', set sent_at, and
    send an email to the client with the circuit presentation.
    """
    from app.models.dossier import Dossier
    from app.services.email_service import EmailService

    # Load trip with photos, cotations, and days
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(
            selectinload(Trip.photos),
            selectinload(Trip.cotations),
            selectinload(Trip.days).selectinload(TripDay.location),
        )
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Circuit non trouvé")

    if trip.status not in ("draft", "quoted"):
        raise HTTPException(
            status_code=400,
            detail=f"Le circuit est déjà en statut '{trip.status}'. Seuls les circuits en brouillon ou devis peuvent être publiés."
        )

    # Check at least one cotation has tarification
    has_tarification = any(
        cot.tarification_json and cot.tarification_json.get("entries")
        for cot in trip.cotations
    ) if trip.cotations else False

    if not has_tarification:
        raise HTTPException(
            status_code=400,
            detail="Le circuit doit avoir au moins une cotation avec une tarification renseignée."
        )

    # Load dossier for client info
    dossier = None
    if trip.dossier_id:
        dossier_result = await db.execute(
            select(Dossier).where(Dossier.id == trip.dossier_id)
        )
        dossier = dossier_result.scalar_one_or_none()

    # Determine client email
    client_email = (body.client_email if body else None) or (
        dossier.client_email if dossier else None
    ) or trip.client_email
    client_name = (dossier.client_name if dossier else None) or trip.client_name or "Cher client"

    # Update trip status
    trip.status = "sent"
    trip.sent_at = datetime.utcnow()

    # Advance dossier status to "quote_sent" if still in early stages
    if dossier and dossier.status in ("lead", "quote_in_progress"):
        dossier.status = "quote_sent"

    # Prepare email data
    # Hero photo
    hero_url = None
    if trip.photos:
        hero = next((p for p in trip.photos if p.is_hero), None) or (trip.photos[0] if trip.photos else None)
        if hero:
            hero_url = hero.url_medium or hero.url_large or hero.url or None

    # Cotation summaries for email
    cotation_data = []
    for cot in sorted(trip.cotations or [], key=lambda c: c.sort_order or 0):
        tarif = cot.tarification_json or {}
        price_label = _build_price_label(
            tarif.get("mode"), tarif.get("entries", []), trip.default_currency
        )
        cotation_data.append({
            "name": cot.name,
            "price_label": price_label,
        })

    # Days summary for email
    days_data = []
    for day in sorted(trip.days or [], key=lambda d: d.sort_order or d.day_number):
        days_data.append({
            "day_number": day.day_number,
            "day_number_end": day.day_number_end,
            "title": day.title,
        })

    # Send email (only if requested)
    should_send = body.send_email if body else True
    email_sent = False
    if should_send and client_email:
        email_service = EmailService()
        email_sent = email_service.send_trip_proposal(
            trip=trip,
            dossier=dossier,
            client_email=client_email,
            client_name=client_name,
            cotations=cotation_data,
            days_summary=days_data,
            hero_photo_url=hero_url,
            portal_url=None,  # TODO: build client portal URL
        )

    await db.commit()

    # Build summary response
    summary = TripSummaryResponse.model_validate(trip)
    # Enrich hero photo
    summary.hero_photo_url = hero_url
    # Enrich cotations
    cot_summaries = []
    for cot in sorted(trip.cotations or [], key=lambda c: c.sort_order or 0):
        tarif = cot.tarification_json or {}
        tarif_mode = tarif.get("mode")
        price_label = _build_price_label(tarif_mode, tarif.get("entries", []), trip.default_currency)
        cot_summaries.append(CotationSummary(
            id=cot.id, name=cot.name, mode=cot.mode,
            tarification_mode=tarif_mode, price_label=price_label,
        ))
    summary.cotations_summary = cot_summaries

    logger.info(
        "Trip %s published (sent) for dossier %s. Email sent: %s",
        trip_id, trip.dossier_id, email_sent,
    )

    return PublishTripResponse(trip=summary, email_sent=email_sent)


# =============================================================================
# Selection options (what can the seller choose?)
# =============================================================================

class SelectionEntry(BaseModel):
    pax_label: Optional[str] = None
    selling_price: Optional[float] = None
    pax_count: Optional[int] = None


class SelectionCotation(BaseModel):
    id: int
    name: str
    mode: str
    tarification_mode: Optional[str] = None
    price_label: Optional[str] = None
    entries: List[SelectionEntry] = []


class SelectionOptionsResponse(BaseModel):
    trip_id: int
    trip_name: str
    cotations: List[SelectionCotation] = []


@router.get("/{trip_id}/selection-options", response_model=SelectionOptionsResponse)
async def get_selection_options(
    trip_id: int,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Get the available selection options for a trip:
    cotations with their pricing entries so the seller can pick
    the right cotation and pax count.
    """
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(selectinload(Trip.cotations))
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Circuit non trouvé")

    cotations_out = []
    for cot in sorted(trip.cotations or [], key=lambda c: c.sort_order or 0):
        tarif = cot.tarification_json or {}
        tarif_mode = tarif.get("mode")
        entries_raw = tarif.get("entries", [])
        price_label = _build_price_label(tarif_mode, entries_raw, trip.default_currency)

        entries = []
        for e in entries_raw:
            # Resolve selling_price from various entry formats:
            # range_web: selling_price, per_person: price_per_person,
            # per_group: group_price, service_list/enumeration: price_per_person
            sp = (
                e.get("selling_price")
                or e.get("price_per_person")
                or e.get("group_price")
                or e.get("unit_price")
            )
            # Resolve pax_count from various entry formats:
            # range_web: pax_min, per_person: total_pax, service_list: pax
            pc = (
                e.get("pax_count")
                or e.get("nb_pax")
                or e.get("total_pax")
                or e.get("pax_min")
                or e.get("pax")
            )
            entries.append(SelectionEntry(
                pax_label=e.get("pax_label") or e.get("label"),
                selling_price=sp,
                pax_count=pc,
            ))

        cotations_out.append(SelectionCotation(
            id=cot.id,
            name=cot.name,
            mode=cot.mode,
            tarification_mode=tarif_mode,
            price_label=price_label,
            entries=entries,
        ))

    return SelectionOptionsResponse(
        trip_id=trip.id,
        trip_name=trip.name,
        cotations=cotations_out,
    )


# =============================================================================
# Select trip (confirm a trip for a dossier)
# =============================================================================

class SelectTripRequest(BaseModel):
    cotation_id: int
    final_pax_count: Optional[int] = None


class SelectTripResponse(BaseModel):
    trip: TripSummaryResponse
    other_trips_cancelled: int


@router.post("/{trip_id}/select", response_model=SelectTripResponse)
async def select_trip(
    trip_id: int,
    body: SelectTripRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Select/confirm a trip proposal for a dossier.

    - Confirms this trip (status → confirmed)
    - Cancels all other trips linked to the same dossier
    - Updates the dossier with selection details
    """
    from app.models.dossier import Dossier

    logger.info("[select_trip] Called with trip_id=%s, cotation_id=%s, final_pax_count=%s",
                trip_id, body.cotation_id, body.final_pax_count)

    # Load trip with cotations
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(
            selectinload(Trip.cotations),
            selectinload(Trip.photos),
        )
    )
    trip = result.scalar_one_or_none()
    if not trip:
        logger.warning("[select_trip] Trip %s not found for tenant %s", trip_id, tenant.id)
        raise HTTPException(status_code=404, detail="Circuit non trouvé")

    logger.info("[select_trip] Trip found: id=%s, status=%s, dossier_id=%s, cotations=%d",
                trip.id, trip.status, trip.dossier_id, len(trip.cotations or []))

    if trip.status not in ("draft", "sent", "confirmed", "quoted"):
        raise HTTPException(
            status_code=400,
            detail=f"Le circuit doit être en statut 'brouillon', 'envoyé' ou 'devis' pour être sélectionné (statut actuel: {trip.status})."
        )

    if not trip.dossier_id:
        raise HTTPException(
            status_code=400,
            detail="Ce circuit n'est rattaché à aucun dossier."
        )

    # Validate cotation exists
    selected_cotation = next(
        (c for c in trip.cotations if c.id == body.cotation_id), None
    )
    if not selected_cotation:
        raise HTTPException(
            status_code=400,
            detail=f"Cotation {body.cotation_id} non trouvée pour ce circuit."
        )

    # Confirm this trip
    trip.status = "confirmed"

    # Cancel other trips for same dossier
    # Use cast to text to avoid PostgreSQL enum comparison issues with asyncpg
    other_trips_result = await db.execute(
        select(Trip).where(
            Trip.dossier_id == trip.dossier_id,
            Trip.tenant_id == tenant.id,
            Trip.id != trip_id,
            Trip.status.cast(SAString).notin_(["cancelled", "completed"]),
        )
    )
    other_trips = list(other_trips_result.scalars().all())
    for other in other_trips:
        other.status = "cancelled"

    # Update dossier selection
    dossier_result = await db.execute(
        select(Dossier).where(Dossier.id == trip.dossier_id)
    )
    dossier = dossier_result.scalar_one_or_none()
    if dossier:
        dossier.selected_trip_id = trip.id
        dossier.selected_cotation_id = selected_cotation.id
        dossier.selected_cotation_name = selected_cotation.name
        dossier.final_pax_count = body.final_pax_count
        dossier.selected_at = datetime.utcnow()
        # Save current status for deselection rollback, then advance to "option"
        if dossier.status in ("lead", "quote_in_progress", "quote_sent", "negotiation", "non_reactive"):
            dossier.status_before_selection = dossier.status
            dossier.status = "option"

    try:
        await db.commit()
        logger.info("[select_trip] DB commit successful")
    except Exception as e:
        logger.error("[select_trip] DB commit failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur lors de la confirmation: {str(e)}")

    # Re-fetch trip with relations to avoid MissingGreenlet after commit
    result2 = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.cotations), selectinload(Trip.photos))
    )
    trip = result2.scalar_one()

    # Build response
    try:
        summary = TripSummaryResponse.model_validate(trip)
        # Enrich hero photo
        if trip.photos:
            hero = next((p for p in trip.photos if p.is_hero), None) or (trip.photos[0] if trip.photos else None)
            if hero:
                summary.hero_photo_url = hero.url_medium or hero.url_large or hero.url or None
        # Enrich cotations
        cot_summaries = []
        for cot in sorted(trip.cotations or [], key=lambda c: c.sort_order or 0):
            tarif = cot.tarification_json or {}
            tarif_mode = tarif.get("mode")
            price_label = _build_price_label(tarif_mode, tarif.get("entries", []), trip.default_currency)
            cot_summaries.append(CotationSummary(
                id=cot.id, name=cot.name, mode=cot.mode,
                tarification_mode=tarif_mode, price_label=price_label,
            ))
        summary.cotations_summary = cot_summaries
    except Exception as e:
        logger.error("[select_trip] Response build failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur lors de la construction de la réponse: {str(e)}")

    logger.info(
        "Trip %s selected for dossier %s. Cotation: %s (%s). %d other trips cancelled.",
        trip_id, trip.dossier_id, selected_cotation.name, body.cotation_id, len(other_trips),
    )

    return SelectTripResponse(
        trip=summary,
        other_trips_cancelled=len(other_trips),
    )


# =============================================================================
# Deselect trip (undo a selection, restore all trips to "sent")
# =============================================================================

class DeselectTripResponse(BaseModel):
    trips_restored: int


@router.post("/{trip_id}/deselect", response_model=DeselectTripResponse)
async def deselect_trip(
    trip_id: int,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Deselect/undo a trip confirmation for a dossier.

    - Reverts this trip from 'confirmed' back to 'sent'
    - Restores all cancelled trips for the same dossier back to 'sent'
    - Clears the dossier selection fields
    - Reverts dossier status to 'quote_sent'
    """
    from app.models.dossier import Dossier

    # Load trip
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Circuit non trouvé")

    if trip.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=f"Seul un circuit confirmé peut être désélectionné (statut actuel: {trip.status})."
        )

    if not trip.dossier_id:
        raise HTTPException(
            status_code=400,
            detail="Ce circuit n'est rattaché à aucun dossier."
        )

    # Revert this trip to "sent"
    trip.status = "sent"

    # Restore cancelled trips for same dossier back to "sent"
    # Use cast to avoid PostgreSQL enum comparison issues with asyncpg
    cancelled_result = await db.execute(
        select(Trip).where(
            Trip.dossier_id == trip.dossier_id,
            Trip.tenant_id == tenant.id,
            Trip.id != trip_id,
            Trip.status.cast(SAString) == "cancelled",
        )
    )
    cancelled_trips = list(cancelled_result.scalars().all())
    for ct in cancelled_trips:
        ct.status = "sent"

    # Clear dossier selection fields
    dossier_result = await db.execute(
        select(Dossier).where(Dossier.id == trip.dossier_id)
    )
    dossier = dossier_result.scalar_one_or_none()
    if dossier:
        dossier.selected_trip_id = None
        dossier.selected_cotation_id = None
        dossier.selected_cotation_name = None
        dossier.final_pax_count = None
        dossier.selected_at = None
        # Revert dossier status to what it was before selection
        if dossier.status in ("option", "confirmed"):
            dossier.status = dossier.status_before_selection or "quote_sent"
        dossier.status_before_selection = None

    await db.commit()

    total_restored = len(cancelled_trips) + 1  # +1 for the confirmed trip itself
    logger.info(
        "Trip %s deselected for dossier %s. %d trips restored to 'sent'.",
        trip_id, trip.dossier_id, total_restored,
    )

    return DeselectTripResponse(trips_restored=total_restored)
