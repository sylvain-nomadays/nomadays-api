"""
Quotation endpoint - triggers the quotation engine for a trip.

Features:
- Multi-currency support with automatic conversion
- Advanced VAT calculation (on_margin vs on_selling_price)
- Item-level VAT recovery for TTC purchases
- Multi-commission structure (primary + secondary)
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentTenant
from app.models.trip import Trip, TripDay, TripPaxConfig
from app.models.formula import Formula
from app.models.item import Item
from app.services.quotation_engine import QuotationEngine, MissingExchangeRateError

router = APIRouter()


# Response schemas
class ItemCostDetail(BaseModel):
    item_id: int
    item_name: str
    unit_cost_local: float  # Cost in original currency
    unit_cost: float  # Cost in selling currency
    quantity: float
    subtotal_cost_local: float
    subtotal_cost: float
    unit_price: float
    subtotal_price: float
    margin_applied: float
    pricing_method: str
    item_currency: str
    exchange_rate: float
    vat_recoverable: float = 0.0


class FormulaCostDetail(BaseModel):
    formula_id: int
    formula_name: str
    items: List[ItemCostDetail]
    total_cost: float
    total_price: float


class DayCostDetail(BaseModel):
    day_id: int
    day_number: int
    title: str | None
    formulas: List[FormulaCostDetail]
    total_cost: float
    total_price: float


class VatDetail(BaseModel):
    """VAT calculation breakdown."""
    margin: float
    vat_base: float
    vat_amount: float
    vat_recoverable: float
    net_vat: float
    price_ttc: float


class CommissionDetail(BaseModel):
    """Commission calculation breakdown."""
    gross_price: float
    primary_commission: float
    primary_commission_label: str
    secondary_commission: float
    secondary_commission_label: str
    total_commissions: float
    net_price: float


class PaxConfigResult(BaseModel):
    pax_config_id: int
    label: str
    total_pax: int
    args: Dict[str, int]
    days: List[DayCostDetail]
    total_cost: float
    total_price: float
    total_profit: float
    cost_per_person: float
    price_per_person: float
    margin_pct: float
    # New: VAT and commission details
    vat: Optional[VatDetail] = None
    commissions: Optional[CommissionDetail] = None
    price_ttc: float = 0.0


class QuotationResponse(BaseModel):
    trip_id: int
    trip_name: str
    currency: str
    margin_type: str
    default_margin_pct: float
    vat_calculation_mode: str = "on_margin"
    primary_commission_pct: float = 0.0
    secondary_commission_pct: Optional[float] = None
    pax_configs: List[PaxConfigResult]
    warnings: List[str] = []
    missing_exchange_rates: List[str] = []


@router.post("/{trip_id}/calculate", response_model=QuotationResponse)
async def calculate_quotation(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Calculate the full quotation for a trip across all pax configurations.

    This endpoint:
    1. Loads the trip with all its structure (days, formulas, items, pax configs)
    2. For each pax config, calculates costs using the quotation engine
    3. Returns detailed cost breakdown and totals
    """
    # Load trip with full structure
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(
            selectinload(Trip.days)
            .selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.seasons),
            selectinload(Trip.pax_configs),
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Initialize quotation engine
    engine = QuotationEngine(
        default_margin_pct=float(trip.margin_pct),
        margin_type=trip.margin_type,
        currency=trip.default_currency,
        duration_days=trip.duration_days,
        start_date=trip.start_date,
    )

    # Get trip settings for VAT and commissions
    vat_pct = float(trip.vat_pct) if trip.vat_pct else 0.0
    vat_calculation_mode = getattr(trip, "vat_calculation_mode", "on_margin") or "on_margin"
    primary_commission_pct = float(getattr(trip, "primary_commission_pct", 0) or 0)
    primary_commission_label = getattr(trip, "primary_commission_label", "") or ""
    secondary_commission_pct = getattr(trip, "secondary_commission_pct", None)
    secondary_commission_label = getattr(trip, "secondary_commission_label", "") or ""

    # Calculate for each pax config
    pax_results = []
    warnings = []
    missing_rates = []

    for pax_config in trip.pax_configs:
        pax_args = pax_config.args_json or {}
        total_pax = pax_config.total_pax

        # Use config-specific margin if set
        effective_margin = (
            float(pax_config.margin_override_pct)
            if pax_config.margin_override_pct is not None
            else float(trip.margin_pct)
        )

        # Calculate each day
        days_detail = []
        config_total_cost = Decimal("0")
        config_total_price = Decimal("0")
        config_vat_recoverable = Decimal("0")

        for day in sorted(trip.days, key=lambda d: d.sort_order):
            formulas_detail = []
            day_total_cost = Decimal("0")
            day_total_price = Decimal("0")

            for formula in sorted(day.formulas, key=lambda f: f.sort_order):
                items_detail = []
                formula_total_cost = Decimal("0")
                formula_total_price = Decimal("0")

                for item in sorted(formula.items, key=lambda i: i.sort_order):
                    # Calculate item cost with currency conversion
                    try:
                        item_result = engine.calculate_item(
                            item=item,
                            pax_args=pax_args,
                            total_pax=total_pax,
                            formula=formula,
                            trip=trip,
                        )
                    except MissingExchangeRateError as e:
                        # Track missing rates but continue with local currency
                        if e.from_currency not in missing_rates:
                            missing_rates.append(e.from_currency)
                            warnings.append(e.message)
                        # Fallback: use rate of 1 (no conversion)
                        item_result = {
                            "unit_cost_local": item.unit_cost or Decimal("0"),
                            "unit_cost": item.unit_cost or Decimal("0"),
                            "quantity": Decimal("1"),
                            "subtotal_cost_local": item.unit_cost or Decimal("0"),
                            "subtotal_cost": item.unit_cost or Decimal("0"),
                            "item_currency": getattr(item, "currency", "EUR"),
                            "selling_currency": trip.default_currency or "EUR",
                            "exchange_rate": Decimal("1.00"),
                            "vat_recoverable": Decimal("0.00"),
                            "warnings": [],
                        }

                    # Apply margin
                    item_cost = item_result["subtotal_cost"]
                    item_price = engine.apply_margin(
                        cost=item_cost,
                        margin_pct=effective_margin,
                        pricing_method=item.pricing_method,
                        pricing_value=float(item.pricing_value) if item.pricing_value else None,
                    )

                    items_detail.append(ItemCostDetail(
                        item_id=item.id,
                        item_name=item.name,
                        unit_cost_local=float(item_result["unit_cost_local"]),
                        unit_cost=float(item_result["unit_cost"]),
                        quantity=float(item_result["quantity"]),
                        subtotal_cost_local=float(item_result["subtotal_cost_local"]),
                        subtotal_cost=float(item_cost),
                        unit_price=float(item_price / item_result["quantity"]) if item_result["quantity"] > 0 else 0,
                        subtotal_price=float(item_price),
                        margin_applied=effective_margin,
                        pricing_method=item.pricing_method,
                        item_currency=item_result["item_currency"],
                        exchange_rate=float(item_result["exchange_rate"]),
                        vat_recoverable=float(item_result["vat_recoverable"]),
                    ))

                    formula_total_cost += item_cost
                    formula_total_price += item_price
                    config_vat_recoverable += item_result["vat_recoverable"]

                    # Collect warnings
                    if item_result.get("warnings"):
                        warnings.extend(item_result["warnings"])

                formulas_detail.append(FormulaCostDetail(
                    formula_id=formula.id,
                    formula_name=formula.name,
                    items=items_detail,
                    total_cost=float(formula_total_cost),
                    total_price=float(formula_total_price),
                ))

                day_total_cost += formula_total_cost
                day_total_price += formula_total_price

            days_detail.append(DayCostDetail(
                day_id=day.id,
                day_number=day.day_number,
                title=day.title,
                formulas=formulas_detail,
                total_cost=float(day_total_cost),
                total_price=float(day_total_price),
            ))

            config_total_cost += day_total_cost
            config_total_price += day_total_price

        # Calculate totals for this pax config
        total_profit = config_total_price - config_total_cost
        cost_per_person = config_total_cost / total_pax if total_pax > 0 else Decimal("0")
        price_per_person = config_total_price / total_pax if total_pax > 0 else Decimal("0")
        actual_margin = (
            (total_profit / config_total_price * 100)
            if config_total_price > 0
            else Decimal("0")
        )

        # Calculate VAT
        vat_detail = None
        price_ttc = config_total_price
        if vat_pct > 0:
            vat_result = engine.calculate_vat_advanced(
                total_cost=config_total_cost,
                total_price=config_total_price,
                vat_pct=vat_pct,
                vat_calculation_mode=vat_calculation_mode,
                primary_commission_pct=primary_commission_pct,
                vat_recoverable=config_vat_recoverable,
            )
            vat_detail = VatDetail(
                margin=float(vat_result["margin"]),
                vat_base=float(vat_result["vat_base"]),
                vat_amount=float(vat_result["vat_amount"]),
                vat_recoverable=float(vat_result["vat_recoverable"]),
                net_vat=float(vat_result["net_vat"]),
                price_ttc=float(vat_result["price_ttc"]),
            )
            price_ttc = vat_result["price_ttc"]

        # Calculate commissions
        commission_detail = None
        if primary_commission_pct > 0 or (secondary_commission_pct and secondary_commission_pct > 0):
            comm_result = engine.calculate_commissions(
                price=config_total_price,
                primary_commission_pct=primary_commission_pct,
                primary_commission_label=primary_commission_label,
                secondary_commission_pct=float(secondary_commission_pct) if secondary_commission_pct else 0,
                secondary_commission_label=secondary_commission_label,
            )
            commission_detail = CommissionDetail(
                gross_price=float(comm_result["gross_price"]),
                primary_commission=float(comm_result["primary_commission"]),
                primary_commission_label=comm_result["primary_commission_label"],
                secondary_commission=float(comm_result["secondary_commission"]),
                secondary_commission_label=comm_result["secondary_commission_label"],
                total_commissions=float(comm_result["total_commissions"]),
                net_price=float(comm_result["net_price"]),
            )

        pax_results.append(PaxConfigResult(
            pax_config_id=pax_config.id,
            label=pax_config.label,
            total_pax=total_pax,
            args=pax_args,
            days=days_detail,
            total_cost=float(config_total_cost),
            total_price=float(config_total_price),
            total_profit=float(total_profit),
            cost_per_person=float(cost_per_person),
            price_per_person=float(price_per_person),
            margin_pct=float(actual_margin),
            vat=vat_detail,
            commissions=commission_detail,
            price_ttc=float(price_ttc),
        ))

        # Update pax_config in DB with calculated values
        pax_config.total_cost = config_total_cost
        pax_config.total_price = config_total_price
        pax_config.total_profit = total_profit
        pax_config.cost_per_person = cost_per_person
        pax_config.price_per_person = price_per_person

    await db.commit()

    return QuotationResponse(
        trip_id=trip.id,
        trip_name=trip.name,
        currency=trip.default_currency,
        margin_type=trip.margin_type,
        default_margin_pct=float(trip.margin_pct),
        vat_calculation_mode=vat_calculation_mode,
        primary_commission_pct=primary_commission_pct,
        secondary_commission_pct=float(secondary_commission_pct) if secondary_commission_pct else None,
        pax_configs=pax_results,
        warnings=list(set(warnings)),
        missing_exchange_rates=missing_rates,
    )


@router.post("/{trip_id}/simulate")
async def simulate_quotation(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    pax_args: Dict[str, int],
    margin_override: float | None = None,
):
    """
    Simulate quotation for a specific pax configuration without saving.

    Useful for quick "what-if" calculations from the UI.
    """
    # Load trip with structure
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(
            selectinload(Trip.days)
            .selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.seasons),
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Calculate total pax from args
    total_pax = sum(pax_args.values())
    if total_pax <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Total pax must be greater than 0",
        )

    # Initialize engine
    engine = QuotationEngine(
        default_margin_pct=margin_override or float(trip.margin_pct),
        margin_type=trip.margin_type,
        currency=trip.default_currency,
        duration_days=trip.duration_days,
        start_date=trip.start_date,
    )

    # Quick calculation (simplified response)
    total_cost = Decimal("0")
    total_price = Decimal("0")

    for day in trip.days:
        for formula in day.formulas:
            for item in formula.items:
                item_result = engine.calculate_item(
                    item=item,
                    pax_args=pax_args,
                    total_pax=total_pax,
                    formula=formula,
                    trip=trip,
                )
                item_cost = item_result["subtotal_cost"]
                item_price = engine.apply_margin(
                    cost=item_cost,
                    margin_pct=margin_override or float(trip.margin_pct),
                    pricing_method=item.pricing_method,
                    pricing_value=float(item.pricing_value) if item.pricing_value else None,
                )
                total_cost += item_cost
                total_price += item_price

    return {
        "total_pax": total_pax,
        "pax_args": pax_args,
        "total_cost": float(total_cost),
        "total_price": float(total_price),
        "total_profit": float(total_price - total_cost),
        "cost_per_person": float(total_cost / total_pax),
        "price_per_person": float(total_price / total_pax),
        "margin_pct": float((total_price - total_cost) / total_price * 100) if total_price > 0 else 0,
    }
