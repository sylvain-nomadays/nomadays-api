"""
Cotations API — CRUD + calculation for named quotation profiles.

A cotation is a named pricing scenario (e.g., "Budget", "Classique", "Deluxe")
with its own set of condition selections and auto-generated pax configurations.
"""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentTenant
from app.models.cotation import TripCotation
from app.models.trip import Trip, TripDay
from app.models.formula import Formula
from app.models.item import Item
from app.models.condition import TripCondition, ConditionOption
from app.models.country_vat_rate import CountryVatRate
from app.models.pax_category import PaxCategory
from app.services.quotation_engine import QuotationEngine
from app.services.quotation_calculator import calculate_for_pax_config
from app.services.pax_generator import generate_pax_configs, generate_custom_config, build_pax_args, format_args_label
from app.services.tarification_engine import compute_tarification

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CotationCreate(BaseModel):
    name: str
    condition_selections: Dict[str, int] = {}
    mode: str = "range"  # "range" or "custom"
    # Mode range
    min_pax: int = 2
    max_pax: int = 10
    # Mode custom
    adult: Optional[int] = None
    teen: Optional[int] = None
    child: Optional[int] = None
    baby: Optional[int] = None
    guide: Optional[int] = None      # None = auto-calculate
    driver: Optional[int] = None     # None = auto-calculate
    # Room demand override (optional, both modes)
    room_demand_override: Optional[list] = None


class CotationUpdate(BaseModel):
    name: Optional[str] = None
    condition_selections: Optional[Dict[str, int]] = None
    min_pax: Optional[int] = None
    max_pax: Optional[int] = None
    pax_configs_json: Optional[list] = None
    sort_order: Optional[int] = None
    room_demand_override: Optional[list] = None


class CotationResponse(BaseModel):
    id: int
    trip_id: int
    name: str
    sort_order: int
    mode: str
    condition_selections: dict
    min_pax: int
    max_pax: int
    pax_configs_json: list
    room_demand_override: Optional[list] = None
    results_json: Optional[dict] = None
    tarification_json: Optional[dict] = None
    status: str
    calculated_at: Optional[str] = None
    created_at: str
    updated_at: str


# Tarification schemas
class TarificationSave(BaseModel):
    """Save tarification data to a cotation."""
    mode: str  # range_web, per_person, per_group, service_list, enumeration
    entries: list  # Entry objects (structure depends on mode)
    validity_date: Optional[str] = None  # ISO date (YYYY-MM-DD) — optional tariff expiry


class TarificationComputedLine(BaseModel):
    """Computed margin result for a single tarification line."""
    label: Optional[str] = None
    selling_price: float
    total_cost: float
    margin_total: float
    margin_pct: float
    primary_commission_amount: float = 0
    secondary_commission_amount: float = 0
    commission_amount: float
    agency_selling_price: float = 0
    margin_after_commission: float
    vat_forecast: float
    vat_recoverable: float
    net_vat: float
    margin_nette: float


class TarificationComputeResponse(BaseModel):
    """Full computed tarification result."""
    lines: List[TarificationComputedLine]
    totals: TarificationComputedLine


def _cotation_to_response(cotation: TripCotation) -> CotationResponse:
    """Convert a TripCotation ORM object to a CotationResponse."""
    return CotationResponse(
        id=cotation.id,
        trip_id=cotation.trip_id,
        name=cotation.name,
        sort_order=cotation.sort_order or 0,
        mode=cotation.mode or "range",
        condition_selections=cotation.condition_selections_json or {},
        min_pax=cotation.min_pax or 2,
        max_pax=cotation.max_pax or 10,
        pax_configs_json=cotation.pax_configs_json or [],
        room_demand_override=cotation.room_demand_override_json,
        results_json=cotation.results_json,
        tarification_json=cotation.tarification_json,
        status=cotation.status or "draft",
        calculated_at=cotation.calculated_at.isoformat() if cotation.calculated_at else None,
        created_at=cotation.created_at.isoformat() if cotation.created_at else "",
        updated_at=cotation.updated_at.isoformat() if cotation.updated_at else "",
    )


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/trips/{trip_id}", response_model=List[CotationResponse])
async def list_cotations(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """List all cotations for a trip."""
    result = await db.execute(
        select(TripCotation)
        .where(TripCotation.trip_id == trip_id, TripCotation.tenant_id == tenant.id)
        .order_by(TripCotation.sort_order)
    )
    cotations = result.scalars().all()
    return [_cotation_to_response(c) for c in cotations]


@router.post("/trips/{trip_id}", response_model=CotationResponse, status_code=201)
async def create_cotation(
    trip_id: int,
    data: CotationCreate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Create a new cotation with auto-generated pax configs."""
    # Verify trip exists
    trip_result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Get next sort_order
    existing = await db.execute(
        select(TripCotation)
        .where(TripCotation.trip_id == trip_id, TripCotation.tenant_id == tenant.id)
    )
    existing_count = len(existing.scalars().all())

    # Generate pax configs based on mode
    if data.mode == "custom":
        pax_configs = generate_custom_config(
            adult=data.adult or 2,
            teen=data.teen or 0,
            child=data.child or 0,
            baby=data.baby or 0,
            guide=data.guide,
            driver=data.driver,
            rooms=data.room_demand_override,
        )
    else:
        pax_configs = generate_pax_configs(data.min_pax, data.max_pax)

    cotation = TripCotation(
        tenant_id=tenant.id,
        trip_id=trip_id,
        name=data.name,
        sort_order=existing_count,
        mode=data.mode,
        condition_selections_json=data.condition_selections,
        min_pax=data.min_pax,
        max_pax=data.max_pax,
        pax_configs_json=pax_configs,
        room_demand_override_json=data.room_demand_override,
        status="draft",
    )
    db.add(cotation)
    await db.commit()
    await db.refresh(cotation)

    logger.info(f"Created cotation '{data.name}' (mode={data.mode}) for trip {trip_id} with {len(pax_configs)} pax configs")
    return _cotation_to_response(cotation)


@router.patch("/{cotation_id}", response_model=CotationResponse)
async def update_cotation(
    cotation_id: int,
    data: CotationUpdate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Update a cotation. If pax range changes, regenerate pax configs."""
    result = await db.execute(
        select(TripCotation)
        .where(TripCotation.id == cotation_id, TripCotation.tenant_id == tenant.id)
    )
    cotation = result.scalar_one_or_none()
    if not cotation:
        raise HTTPException(status_code=404, detail="Cotation not found")

    # Track if pax range changed
    pax_range_changed = False

    if data.name is not None:
        cotation.name = data.name
    if data.condition_selections is not None:
        cotation.condition_selections_json = data.condition_selections
        # Invalidate results when conditions change
        cotation.status = "draft"
        cotation.results_json = None
    if data.min_pax is not None and data.min_pax != cotation.min_pax:
        cotation.min_pax = data.min_pax
        pax_range_changed = True
    if data.max_pax is not None and data.max_pax != cotation.max_pax:
        cotation.max_pax = data.max_pax
        pax_range_changed = True
    if data.pax_configs_json is not None:
        cotation.pax_configs_json = data.pax_configs_json
        cotation.status = "draft"
        cotation.results_json = None
    if data.sort_order is not None:
        cotation.sort_order = data.sort_order
    if data.room_demand_override is not None:
        cotation.room_demand_override_json = data.room_demand_override

    # Regenerate pax configs if range changed (only for range mode)
    if pax_range_changed and (cotation.mode or "range") == "range":
        cotation.pax_configs_json = generate_pax_configs(cotation.min_pax, cotation.max_pax)
        cotation.status = "draft"
        cotation.results_json = None

    await db.commit()
    await db.refresh(cotation)
    return _cotation_to_response(cotation)


@router.delete("/{cotation_id}", status_code=204)
async def delete_cotation(
    cotation_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Delete a cotation."""
    result = await db.execute(
        select(TripCotation)
        .where(TripCotation.id == cotation_id, TripCotation.tenant_id == tenant.id)
    )
    cotation = result.scalar_one_or_none()
    if not cotation:
        raise HTTPException(status_code=404, detail="Cotation not found")

    await db.delete(cotation)
    await db.commit()


@router.post("/{cotation_id}/regenerate-pax", response_model=CotationResponse)
async def regenerate_pax_configs(
    cotation_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Regenerate pax configs from current min/max range (range mode only)."""
    result = await db.execute(
        select(TripCotation)
        .where(TripCotation.id == cotation_id, TripCotation.tenant_id == tenant.id)
    )
    cotation = result.scalar_one_or_none()
    if not cotation:
        raise HTTPException(status_code=404, detail="Cotation not found")

    # Custom mode: composition is fixed, cannot regenerate
    if (cotation.mode or "range") == "custom":
        raise HTTPException(
            status_code=400,
            detail="Cannot regenerate pax configs for custom mode cotations. The composition is fixed.",
        )

    cotation.pax_configs_json = generate_pax_configs(cotation.min_pax, cotation.max_pax)
    cotation.status = "draft"
    cotation.results_json = None

    await db.commit()
    await db.refresh(cotation)
    return _cotation_to_response(cotation)


# ---------------------------------------------------------------------------
# Calculation endpoints
# ---------------------------------------------------------------------------

async def _load_trip_for_calculation(
    trip_id: int,
    tenant_id: Any,
    db: DbSession,
) -> Optional[Any]:
    """Load a trip with full eager-loaded structure for calculation."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant_id)
        .options(
            # Day-level formulas with items, seasons, and price tiers
            selectinload(Trip.days)
            .selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.seasons),
            selectinload(Trip.days)
            .selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.price_tiers),
            selectinload(Trip.days)
            .selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.condition_option),
            selectinload(Trip.days)
            .selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.cost_nature),
            # Transversal formulas
            selectinload(Trip.transversal_formulas)
            .selectinload(Formula.items)
            .selectinload(Item.seasons),
            selectinload(Trip.transversal_formulas)
            .selectinload(Formula.items)
            .selectinload(Item.price_tiers),
            selectinload(Trip.transversal_formulas)
            .selectinload(Formula.items)
            .selectinload(Item.condition_option),
            selectinload(Trip.transversal_formulas)
            .selectinload(Formula.items)
            .selectinload(Item.cost_nature),
            # Trip conditions
            selectinload(Trip.trip_conditions)
            .selectinload(TripCondition.selected_option),
        )
    )
    return result.scalar_one_or_none()


async def _build_conditions_map(
    trip: Any,
    cotation: TripCotation,
    db: DbSession,
) -> Dict[int, Any]:
    """
    Build a conditions map merging trip-level defaults with cotation overrides.

    Returns a dict mapping condition_id → object with selected_option_id, is_active, selected_option.
    """
    # Start with trip-level conditions
    conditions_map: Dict[int, Any] = {
        tc.condition_id: tc for tc in (trip.trip_conditions or [])
    }

    # Override with cotation-specific selections
    cotation_selections = cotation.condition_selections_json or {}
    for condition_id_str, selected_option_id in cotation_selections.items():
        condition_id = int(condition_id_str)

        # Load the ConditionOption from DB for the should_include_item interface
        option_result = await db.execute(
            select(ConditionOption).where(ConditionOption.id == selected_option_id)
        )
        selected_option = option_result.scalar_one_or_none()

        # Create a lightweight object that satisfies should_include_item() interface
        virtual_condition = SimpleNamespace(
            condition_id=condition_id,
            selected_option_id=selected_option_id,
            is_active=True,
            selected_option=selected_option,
        )
        conditions_map[condition_id] = virtual_condition

    return conditions_map


@router.post("/{cotation_id}/calculate")
async def calculate_cotation(
    cotation_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Run the quotation engine for a single cotation.

    Calculates costs for all pax configs using the cotation's condition overrides.
    Results are stored in cotation.results_json.
    """
    # Load cotation
    cot_result = await db.execute(
        select(TripCotation)
        .where(TripCotation.id == cotation_id, TripCotation.tenant_id == tenant.id)
    )
    cotation = cot_result.scalar_one_or_none()
    if not cotation:
        raise HTTPException(status_code=404, detail="Cotation not found")

    # Mark as calculating
    cotation.status = "calculating"
    await db.commit()

    try:
        # Load trip with full structure
        trip = await _load_trip_for_calculation(cotation.trip_id, tenant.id, db)
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        # Build conditions map with cotation overrides
        trip_conditions_map = await _build_conditions_map(trip, cotation, db)

        # Load country VAT rate
        country_vat_rate = None
        destination_country = getattr(trip, "destination_country", None)
        if destination_country:
            cvr_result = await db.execute(
                select(CountryVatRate).where(
                    CountryVatRate.tenant_id == tenant.id,
                    CountryVatRate.country_code == destination_country,
                    CountryVatRate.is_active == True,
                )
            )
            country_vat_rate = cvr_result.scalar_one_or_none()

        # Load pax categories
        pax_cats_result = await db.execute(
            select(PaxCategory).where(
                PaxCategory.tenant_id == tenant.id,
                PaxCategory.is_active == True,
            )
        )
        pax_categories = pax_cats_result.scalars().all()
        paying_pax_categories = {
            cat.code for cat in pax_categories if cat.counts_for_pricing
        } if pax_categories else None

        # Initialize engine
        engine = QuotationEngine(
            default_margin_pct=float(trip.margin_pct),
            margin_type=trip.margin_type,
            currency=trip.default_currency,
            duration_days=trip.duration_days,
            start_date=trip.start_date,
            paying_pax_categories=paying_pax_categories,
        )

        # Trip settings
        vat_pct = float(trip.vat_pct) if trip.vat_pct else 0.0
        vat_calculation_mode = getattr(trip, "vat_calculation_mode", "on_margin") or "on_margin"
        primary_commission_pct = float(getattr(trip, "primary_commission_pct", 0) or 0)
        primary_commission_label = getattr(trip, "primary_commission_label", "") or ""
        secondary_commission_pct = getattr(trip, "secondary_commission_pct", None)
        secondary_commission_label = getattr(trip, "secondary_commission_label", "") or ""

        # Calculate for each pax config
        pax_results = []
        all_warnings = []
        all_missing_rates = []

        for config in (cotation.pax_configs_json or []):
            pax_args = build_pax_args(config)
            total_pax = config.get("total_pax", sum(pax_args.values()))

            # Use trip default margin (cotation inherits trip margin)
            effective_margin = float(trip.margin_pct)

            result, warnings, missing_rates = calculate_for_pax_config(
                pax_args=pax_args,
                total_pax=total_pax,
                effective_margin=effective_margin,
                trip=trip,
                trip_conditions_map=trip_conditions_map,
                engine=engine,
                country_vat_rate=country_vat_rate,
                vat_pct=vat_pct,
                vat_calculation_mode=vat_calculation_mode,
                primary_commission_pct=primary_commission_pct,
                primary_commission_label=primary_commission_label,
                secondary_commission_pct=secondary_commission_pct,
                secondary_commission_label=secondary_commission_label,
            )

            # Add label and args label
            result["label"] = config.get("label", f"{config.get('adult', 0)} pax")
            result["args_label"] = format_args_label(config)
            result["margin_default"] = effective_margin

            pax_results.append(result)
            all_warnings.extend(warnings)
            all_missing_rates.extend(missing_rates)

        # Store results
        cotation.results_json = {
            "trip_id": trip.id,
            "trip_name": trip.name,
            "currency": trip.default_currency or "EUR",
            "margin_type": trip.margin_type or "margin",
            "default_margin_pct": float(trip.margin_pct),
            "pax_configs": pax_results,
            "warnings": list(set(all_warnings)),
            "missing_exchange_rates": list(set(all_missing_rates)),
        }
        cotation.status = "calculated"
        cotation.calculated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(cotation)

        logger.info(
            f"Calculated cotation '{cotation.name}' (id={cotation.id}) "
            f"for trip {cotation.trip_id}: {len(pax_results)} pax configs"
        )

        return _cotation_to_response(cotation)

    except Exception as e:
        cotation.status = "error"
        await db.commit()
        logger.error(f"Cotation calculation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Calculation failed: {str(e)}",
        )


@router.post("/trips/{trip_id}/calculate-all")
async def calculate_all_cotations(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Calculate all cotations for a trip."""
    # Load all cotations
    result = await db.execute(
        select(TripCotation)
        .where(TripCotation.trip_id == trip_id, TripCotation.tenant_id == tenant.id)
        .order_by(TripCotation.sort_order)
    )
    cotations = result.scalars().all()

    if not cotations:
        raise HTTPException(status_code=404, detail="No cotations found for this trip")

    # Load trip once
    trip = await _load_trip_for_calculation(trip_id, tenant.id, db)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Load shared resources
    country_vat_rate = None
    destination_country = getattr(trip, "destination_country", None)
    if destination_country:
        cvr_result = await db.execute(
            select(CountryVatRate).where(
                CountryVatRate.tenant_id == tenant.id,
                CountryVatRate.country_code == destination_country,
                CountryVatRate.is_active == True,
            )
        )
        country_vat_rate = cvr_result.scalar_one_or_none()

    pax_cats_result = await db.execute(
        select(PaxCategory).where(
            PaxCategory.tenant_id == tenant.id,
            PaxCategory.is_active == True,
        )
    )
    pax_categories = pax_cats_result.scalars().all()
    paying_pax_categories = {
        cat.code for cat in pax_categories if cat.counts_for_pricing
    } if pax_categories else None

    engine = QuotationEngine(
        default_margin_pct=float(trip.margin_pct),
        margin_type=trip.margin_type,
        currency=trip.default_currency,
        duration_days=trip.duration_days,
        start_date=trip.start_date,
        paying_pax_categories=paying_pax_categories,
    )

    vat_pct = float(trip.vat_pct) if trip.vat_pct else 0.0
    vat_calculation_mode = getattr(trip, "vat_calculation_mode", "on_margin") or "on_margin"
    primary_commission_pct = float(getattr(trip, "primary_commission_pct", 0) or 0)
    primary_commission_label = getattr(trip, "primary_commission_label", "") or ""
    secondary_commission_pct = getattr(trip, "secondary_commission_pct", None)
    secondary_commission_label = getattr(trip, "secondary_commission_label", "") or ""

    results = []
    for cotation in cotations:
        try:
            cotation.status = "calculating"
            trip_conditions_map = await _build_conditions_map(trip, cotation, db)

            pax_results = []
            all_warnings = []
            all_missing_rates = []

            for config in (cotation.pax_configs_json or []):
                pax_args = build_pax_args(config)
                total_pax = config.get("total_pax", sum(pax_args.values()))
                effective_margin = float(trip.margin_pct)

                calc_result, warnings, missing_rates = calculate_for_pax_config(
                    pax_args=pax_args,
                    total_pax=total_pax,
                    effective_margin=effective_margin,
                    trip=trip,
                    trip_conditions_map=trip_conditions_map,
                    engine=engine,
                    country_vat_rate=country_vat_rate,
                    vat_pct=vat_pct,
                    vat_calculation_mode=vat_calculation_mode,
                    primary_commission_pct=primary_commission_pct,
                    primary_commission_label=primary_commission_label,
                    secondary_commission_pct=secondary_commission_pct,
                    secondary_commission_label=secondary_commission_label,
                )

                calc_result["label"] = config.get("label", f"{config.get('adult', 0)} pax")
                calc_result["args_label"] = format_args_label(config)
                calc_result["margin_default"] = effective_margin
                pax_results.append(calc_result)
                all_warnings.extend(warnings)
                all_missing_rates.extend(missing_rates)

            cotation.results_json = {
                "trip_id": trip.id,
                "trip_name": trip.name,
                "currency": trip.default_currency or "EUR",
                "margin_type": trip.margin_type or "margin",
                "default_margin_pct": float(trip.margin_pct),
                "pax_configs": pax_results,
                "warnings": list(set(all_warnings)),
                "missing_exchange_rates": list(set(all_missing_rates)),
            }
            cotation.status = "calculated"
            cotation.calculated_at = datetime.now(timezone.utc)
            results.append(_cotation_to_response(cotation))

        except Exception as e:
            cotation.status = "error"
            logger.error(f"Cotation '{cotation.name}' calculation failed: {e}", exc_info=True)
            results.append(_cotation_to_response(cotation))

    await db.commit()

    logger.info(f"Calculated {len(results)} cotations for trip {trip_id}")
    return results


# ---------------------------------------------------------------------------
# Tarification endpoints
# ---------------------------------------------------------------------------

@router.patch("/{cotation_id}/tarification", response_model=CotationResponse)
async def save_tarification(
    cotation_id: int,
    data: TarificationSave,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Save tarification data (pricing mode + entries) to a cotation."""
    result = await db.execute(
        select(TripCotation).where(
            TripCotation.id == cotation_id,
            TripCotation.tenant_id == tenant.id,
        )
    )
    cotation = result.scalar_one_or_none()
    if not cotation:
        raise HTTPException(status_code=404, detail="Cotation not found")

    tarif_data: dict = {"mode": data.mode, "entries": data.entries}
    if data.validity_date:
        tarif_data["validity_date"] = data.validity_date
    cotation.tarification_json = tarif_data
    await db.commit()
    await db.refresh(cotation)

    return _cotation_to_response(cotation)


@router.post("/{cotation_id}/tarification/compute", response_model=TarificationComputeResponse)
async def compute_tarification_endpoint(
    cotation_id: int,
    data: TarificationSave,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Compute margin analysis for given tarification entries.

    Uses the cotation's results_json (costs) and trip settings
    to calculate margins, commissions, and VAT forecasts.
    Does NOT save — use PATCH to save.
    """
    # Load cotation with trip
    result = await db.execute(
        select(TripCotation).where(
            TripCotation.id == cotation_id,
            TripCotation.tenant_id == tenant.id,
        )
    )
    cotation = result.scalar_one_or_none()
    if not cotation:
        raise HTTPException(status_code=404, detail="Cotation not found")

    if not cotation.results_json:
        raise HTTPException(
            status_code=400,
            detail="Cotation has no calculated results. Please run calculation first.",
        )

    # Load trip for settings
    trip_result = await db.execute(
        select(Trip).where(Trip.id == cotation.trip_id, Trip.tenant_id == tenant.id)
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    trip_settings = {
        "primary_commission_pct": float(trip.primary_commission_pct or 0),
        "primary_commission_label": trip.primary_commission_label or "",
        "secondary_commission_pct": float(trip.secondary_commission_pct or 0) if trip.secondary_commission_pct else 0,
        "secondary_commission_label": trip.secondary_commission_label or "",
        "vat_pct": float(trip.vat_pct or 0),
        "vat_calculation_mode": trip.vat_calculation_mode or "on_margin",
    }

    tarification_data = {"mode": data.mode, "entries": data.entries}
    computed = compute_tarification(tarification_data, cotation.results_json, trip_settings)

    return TarificationComputeResponse(
        lines=[TarificationComputedLine(**line) for line in computed["lines"]],
        totals=TarificationComputedLine(**computed["totals"]),
    )
