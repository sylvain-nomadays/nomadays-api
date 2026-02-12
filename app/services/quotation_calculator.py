"""
Quotation calculator — reusable calculation loop for pax configs.

Extracts the core calculation logic from quotation.py so it can be reused
by both the existing POST /quotation/{trip_id}/calculate endpoint and
the new POST /cotations/{cotation_id}/calculate endpoint.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional, Set, Tuple

from app.services.quotation_engine import QuotationEngine, MissingExchangeRateError


# ---------------------------------------------------------------------------
# Lightweight result containers (plain dicts for serialization flexibility)
# ---------------------------------------------------------------------------

def calculate_for_pax_config(
    *,
    pax_args: Dict[str, int],
    total_pax: int,
    effective_margin: float,
    trip: Any,
    trip_conditions_map: Dict[int, Any],
    engine: QuotationEngine,
    country_vat_rate: Any = None,
    vat_pct: float = 0.0,
    vat_calculation_mode: str = "on_margin",
    primary_commission_pct: float = 0.0,
    primary_commission_label: str = "",
    secondary_commission_pct: Optional[float] = None,
    secondary_commission_label: str = "",
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """
    Run the quotation engine for a single pax config.

    Returns:
        (result_dict, warnings, missing_rates)
        where result_dict contains all the calculated values.
    """
    warnings: List[str] = []
    missing_rates: List[str] = []

    days_detail = []
    config_total_cost = Decimal("0")
    config_total_price = Decimal("0")
    config_vat_recoverable = Decimal("0")
    config_vat_surcharge = Decimal("0")

    # ---- Day-level formulas ----
    for day in sorted(trip.days, key=lambda d: d.sort_order):
        formulas_detail = []
        day_total_cost = Decimal("0")
        day_total_price = Decimal("0")

        for formula in sorted(day.formulas, key=lambda f: f.sort_order):
            formula_result = _calculate_formula(
                formula=formula,
                pax_args=pax_args,
                total_pax=total_pax,
                effective_margin=effective_margin,
                trip=trip,
                trip_conditions_map=trip_conditions_map,
                engine=engine,
                country_vat_rate=country_vat_rate,
                warnings=warnings,
                missing_rates=missing_rates,
            )

            formulas_detail.append({
                "formula_id": formula.id,
                "formula_name": formula.name,
                "items": formula_result["items"],
                "total_cost": float(formula_result["total_cost"]),
                "total_price": float(formula_result["total_price"]),
            })

            day_total_cost += formula_result["total_cost"]
            day_total_price += formula_result["total_price"]
            config_vat_recoverable += formula_result["vat_recoverable"]
            config_vat_surcharge += formula_result.get("vat_surcharge", Decimal("0"))

        days_detail.append({
            "day_id": day.id,
            "day_number": day.day_number,
            "title": day.title,
            "formulas": formulas_detail,
            "total_cost": float(day_total_cost),
            "total_price": float(day_total_price),
        })

        config_total_cost += day_total_cost
        config_total_price += day_total_price

    # ---- Transversal formulas ----
    transversal_detail = []
    for formula in sorted(
        getattr(trip, "transversal_formulas", []),
        key=lambda f: f.sort_order,
    ):
        formula_result = _calculate_formula(
            formula=formula,
            pax_args=pax_args,
            total_pax=total_pax,
            effective_margin=effective_margin,
            trip=trip,
            trip_conditions_map=trip_conditions_map,
            engine=engine,
            country_vat_rate=country_vat_rate,
            warnings=warnings,
            missing_rates=missing_rates,
        )

        transversal_detail.append({
            "formula_id": formula.id,
            "formula_name": formula.name,
            "items": formula_result["items"],
            "total_cost": float(formula_result["total_cost"]),
            "total_price": float(formula_result["total_price"]),
        })

        config_total_cost += formula_result["total_cost"]
        config_total_price += formula_result["total_price"]
        config_vat_recoverable += formula_result["vat_recoverable"]
        config_vat_surcharge += formula_result.get("vat_surcharge", Decimal("0"))

    # ---- Totals ----
    total_profit = config_total_price - config_total_cost
    paying_pax_count = engine.get_paying_pax(pax_args)
    cost_per_person = config_total_cost / total_pax if total_pax > 0 else Decimal("0")
    price_per_person = config_total_price / total_pax if total_pax > 0 else Decimal("0")
    price_per_paying_person = (
        config_total_price / paying_pax_count
        if paying_pax_count > 0
        else Decimal("0")
    )
    actual_margin = (
        (total_profit / config_total_price * 100)
        if config_total_price > 0
        else Decimal("0")
    )

    # ---- VAT ----
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
        vat_detail = {
            "margin": float(vat_result["margin"]),
            "vat_base": float(vat_result["vat_base"]),
            "vat_amount": float(vat_result["vat_amount"]),
            "vat_recoverable": float(vat_result["vat_recoverable"]),
            "net_vat": float(vat_result["net_vat"]),
            "price_ttc": float(vat_result["price_ttc"]),
        }
        price_ttc = vat_result["price_ttc"]

    # ---- Commissions ----
    commission_detail = None
    if primary_commission_pct > 0 or (secondary_commission_pct and secondary_commission_pct > 0):
        comm_result = engine.calculate_commissions(
            price=config_total_price,
            primary_commission_pct=primary_commission_pct,
            primary_commission_label=primary_commission_label,
            secondary_commission_pct=float(secondary_commission_pct) if secondary_commission_pct else 0,
            secondary_commission_label=secondary_commission_label,
        )
        commission_detail = {
            "gross_price": float(comm_result["gross_price"]),
            "primary_commission": float(comm_result["primary_commission"]),
            "primary_commission_label": comm_result["primary_commission_label"],
            "secondary_commission": float(comm_result["secondary_commission"]),
            "secondary_commission_label": comm_result["secondary_commission_label"],
            "total_commissions": float(comm_result["total_commissions"]),
            "net_price": float(comm_result["net_price"]),
        }

    result = {
        "total_pax": total_pax,
        "paying_pax": paying_pax_count,
        "args": pax_args,
        "days": days_detail,
        "transversal_formulas": transversal_detail,
        "total_cost": float(config_total_cost),
        "total_price": float(config_total_price),
        "total_profit": float(total_profit),
        "cost_per_person": float(cost_per_person),
        "price_per_person": float(price_per_person),
        "price_per_paying_person": float(price_per_paying_person),
        "margin_pct": float(actual_margin),
        "vat": vat_detail,
        "vat_surcharge_total": float(config_vat_surcharge),
        "commissions": commission_detail,
        "price_ttc": float(price_ttc),
    }

    return result, warnings, missing_rates


def _calculate_formula(
    *,
    formula: Any,
    pax_args: Dict[str, int],
    total_pax: int,
    effective_margin: float,
    trip: Any,
    trip_conditions_map: Dict[int, Any],
    engine: QuotationEngine,
    country_vat_rate: Any = None,
    warnings: List[str],
    missing_rates: List[str],
) -> Dict[str, Any]:
    """Calculate all items in a formula, returning totals and item details."""
    items_detail = []
    formula_total_cost = Decimal("0")
    formula_total_price = Decimal("0")
    formula_vat_recoverable = Decimal("0")
    formula_vat_surcharge = Decimal("0")

    for item in sorted(formula.items, key=lambda i: i.sort_order):
        # Check item-level condition
        include, reason = QuotationEngine.should_include_item(
            item, formula, trip_conditions_map
        )
        if not include:
            if reason:
                warnings.append(reason)
            continue

        # Calculate item cost with currency conversion
        try:
            item_result = engine.calculate_item(
                item=item,
                pax_args=pax_args,
                total_pax=total_pax,
                formula=formula,
                trip=trip,
                country_vat_rate=country_vat_rate,
            )
        except MissingExchangeRateError as e:
            if e.from_currency not in missing_rates:
                missing_rates.append(e.from_currency)
                warnings.append(e.message)
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
                "vat_surcharge": Decimal("0.00"),
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

        items_detail.append({
            "item_id": item.id,
            "item_name": item.name,
            "cost_nature_code": getattr(item.cost_nature, "code", "MIS") if item.cost_nature else "MIS",
            "unit_cost_local": float(item_result["unit_cost_local"]),
            "unit_cost": float(item_result["unit_cost"]),
            "quantity": float(item_result["quantity"]),
            "subtotal_cost_local": float(item_result["subtotal_cost_local"]),
            "subtotal_cost": float(item_cost),
            "unit_price": float(item_price / item_result["quantity"]) if item_result["quantity"] > 0 else 0,
            "subtotal_price": float(item_price),
            "margin_applied": effective_margin,
            "pricing_method": item.pricing_method,
            "item_currency": item_result["item_currency"],
            "exchange_rate": float(item_result["exchange_rate"]),
            "vat_recoverable": float(item_result["vat_recoverable"]),
            "vat_surcharge": float(item_result.get("vat_surcharge", 0)),
        })

        formula_total_cost += item_cost
        formula_total_price += item_price
        formula_vat_recoverable += item_result["vat_recoverable"]
        formula_vat_surcharge += item_result.get("vat_surcharge", Decimal("0"))

        if item_result.get("warnings"):
            warnings.extend(item_result["warnings"])

    return {
        "items": items_detail,
        "total_cost": formula_total_cost,
        "total_price": formula_total_price,
        "vat_recoverable": formula_vat_recoverable,
        "vat_surcharge": formula_vat_surcharge,
    }
