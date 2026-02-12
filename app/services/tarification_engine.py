"""
Tarification Engine — Reverse margin calculation.

Given a selling price (set by user) and cost data (from cotation results),
computes margins, commissions, and VAT forecasts.

This is the inverse of the quotation engine:
- Quotation: cost → margin → selling price
- Tarification: selling price → margin (with commission & VAT breakdown)
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Optional

from app.services.quotation_engine import QuotationEngine


def compute_tarification(
    tarification_data: dict,
    cotation_results: dict,
    trip_settings: dict,
) -> dict:
    """
    Compute margin analysis for a tarification.

    Args:
        tarification_data: {"mode": "...", "entries": [...]}
        cotation_results: The cotation's results_json (from calculation)
        trip_settings: {
            "primary_commission_pct": float,
            "primary_commission_label": str,
            "secondary_commission_pct": float,
            "secondary_commission_label": str,
            "vat_pct": float,
            "vat_calculation_mode": str,  # "on_margin" or "on_selling_price"
        }

    Returns:
        {"lines": [...], "totals": {...}}
    """
    mode = tarification_data.get("mode", "range_web")
    entries = tarification_data.get("entries", [])
    pax_configs = cotation_results.get("pax_configs", [])

    commission_pct = Decimal(str(trip_settings.get("primary_commission_pct", 0)))
    commission_label = trip_settings.get("primary_commission_label", "")
    secondary_commission_pct = Decimal(str(trip_settings.get("secondary_commission_pct", 0)))
    secondary_commission_label = trip_settings.get("secondary_commission_label", "")
    vat_pct = Decimal(str(trip_settings.get("vat_pct", 0)))
    vat_mode = trip_settings.get("vat_calculation_mode", "on_margin")

    engine = QuotationEngine()

    lines = []

    if mode == "range_web":
        lines = _compute_range_web(entries, pax_configs, commission_pct, vat_pct, vat_mode, engine, secondary_commission_pct)
    elif mode == "per_person":
        lines = _compute_per_person(entries, pax_configs, commission_pct, vat_pct, vat_mode, engine, secondary_commission_pct)
    elif mode == "per_group":
        lines = _compute_per_group(entries, pax_configs, commission_pct, vat_pct, vat_mode, engine, secondary_commission_pct)
    elif mode == "service_list":
        lines = _compute_service_list(entries, pax_configs, commission_pct, vat_pct, vat_mode, engine, secondary_commission_pct)
    elif mode == "enumeration":
        lines = _compute_enumeration(entries, pax_configs, commission_pct, vat_pct, vat_mode, engine, secondary_commission_pct)

    # Compute totals
    totals = _compute_totals(lines)

    return {"lines": lines, "totals": totals}


def _find_pax_config(pax_configs: list, target_pax: int) -> Optional[dict]:
    """Find the pax_config matching a target pax count."""
    # Exact match first
    for pc in pax_configs:
        if pc.get("total_pax") == target_pax:
            return pc
    # Try paying_pax match
    for pc in pax_configs:
        if pc.get("paying_pax") == target_pax:
            return pc
    # Closest match
    if pax_configs:
        return min(pax_configs, key=lambda pc: abs(pc.get("total_pax", 0) - target_pax))
    return None


def _compute_margin_line(
    label: Optional[str],
    selling_price: Decimal,
    total_cost: Decimal,
    vat_recoverable_from_cotation: Decimal,
    commission_pct: Decimal,
    vat_pct: Decimal,
    vat_mode: str,
    engine: QuotationEngine,
    secondary_commission_pct: Decimal = Decimal("0"),
) -> dict:
    """Compute a single margin line from selling price and cost."""
    margin_total = selling_price - total_cost
    margin_pct = (
        (margin_total / selling_price * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if selling_price > 0 else Decimal("0")
    )

    # Primary commission
    primary_commission_amount = (selling_price * commission_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    # Secondary commission
    secondary_commission_amount = (selling_price * secondary_commission_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    # Total commission = sum of both
    commission_amount = primary_commission_amount + secondary_commission_amount
    # Agency selling price = selling price - total commission
    agency_selling_price = selling_price - commission_amount
    margin_after_commission = margin_total - commission_amount

    # VAT forecast
    vat_forecast = Decimal("0")
    # In on_margin mode, there is no recoverable VAT — only VAT on the margin
    # In on_selling_price mode, VAT recoverable from TTC purchases is deducted
    vat_recoverable = Decimal("0") if vat_mode == "on_margin" else vat_recoverable_from_cotation
    net_vat = Decimal("0")

    # For VAT calculation, use total commission pct
    total_commission_pct = commission_pct + secondary_commission_pct

    if vat_pct > 0:
        vat_result = engine.calculate_vat_advanced(
            total_cost=total_cost,
            total_price=selling_price,
            vat_pct=float(vat_pct),
            vat_calculation_mode=vat_mode,
            primary_commission_pct=float(total_commission_pct),
            vat_recoverable=vat_recoverable,
        )
        vat_forecast = vat_result["vat_amount"]
        net_vat = vat_result["net_vat"]

    margin_nette = margin_after_commission - net_vat

    return {
        "label": label,
        "selling_price": float(selling_price.quantize(Decimal("0.01"))),
        "total_cost": float(total_cost.quantize(Decimal("0.01"))),
        "margin_total": float(margin_total.quantize(Decimal("0.01"))),
        "margin_pct": float(margin_pct),
        "primary_commission_amount": float(primary_commission_amount),
        "secondary_commission_amount": float(secondary_commission_amount),
        "commission_amount": float(commission_amount),
        "agency_selling_price": float(agency_selling_price.quantize(Decimal("0.01"))),
        "margin_after_commission": float(margin_after_commission.quantize(Decimal("0.01"))),
        "vat_forecast": float(vat_forecast),
        "vat_recoverable": float(vat_recoverable.quantize(Decimal("0.01"))),
        "net_vat": float(net_vat),
        "margin_nette": float(margin_nette.quantize(Decimal("0.01"))),
    }


def _get_vat_recoverable(pax_config: dict) -> Decimal:
    """Extract VAT recoverable from a pax_config result."""
    vat_detail = pax_config.get("vat")
    if vat_detail and isinstance(vat_detail, dict):
        return Decimal(str(vat_detail.get("vat_recoverable", 0)))
    return Decimal("0")


def _get_vat_surcharge(pax_config: dict) -> Decimal:
    """Extract total VAT surcharge from a pax_config result.

    The quotation engine adds a surcharge to HT items to protect the margin.
    This surcharge is included in total_cost but is NOT a real supplier cost.
    We must subtract it so the tarification margin reflects the true supplier cost.
    """
    return Decimal(str(pax_config.get("vat_surcharge_total", 0)))


# --- Mode implementations ---

def _compute_range_web(
    entries: list, pax_configs: list,
    commission_pct: Decimal, vat_pct: Decimal, vat_mode: str,
    engine: QuotationEngine,
    secondary_commission_pct: Decimal = Decimal("0"),
) -> list:
    """Range Web: each entry has pax_min/max and a selling_price per person.

    When a range spans multiple pax values (e.g. 4-6), we generate one result
    line per pax value so the user sees the exact margin for each.
    """
    lines = []
    for entry in entries:
        selling_price_pp = Decimal(str(entry.get("selling_price", 0)))
        pax_min = entry.get("pax_min", 1)
        pax_max = entry.get("pax_max", pax_min)
        pax_label = entry.get("pax_label", f"{pax_min}")

        # Expand the range: one line per pax value
        for pax_val in range(pax_min, pax_max + 1):
            pc = _find_pax_config(pax_configs, pax_val)
            if not pc:
                continue

            paying_pax = pc.get("paying_pax", pc.get("total_pax", pax_val))
            total_cost_raw = Decimal(str(pc.get("total_cost", 0)))
            vat_surcharge = _get_vat_surcharge(pc)
            # Use real supplier cost (without VAT surcharge) for margin calculation
            total_cost = total_cost_raw - vat_surcharge
            selling_price_total = selling_price_pp * paying_pax
            vat_recov = _get_vat_recoverable(pc)

            total_pax_count = pc.get("total_pax", pax_val)
            cost_per_person = (total_cost / total_pax_count).quantize(Decimal("0.01")) if total_pax_count > 0 else Decimal("0")

            # Label: just the pax value (grouping header handles the range context)
            label = str(pax_val)

            line = _compute_margin_line(
                label=label,
                selling_price=selling_price_total,
                total_cost=total_cost,
                vat_recoverable_from_cotation=vat_recov,
                commission_pct=commission_pct,
                vat_pct=vat_pct,
                vat_mode=vat_mode,
                engine=engine,
                secondary_commission_pct=secondary_commission_pct,
            )
            # Also add per-person info
            line["selling_price_per_person"] = float(selling_price_pp)
            line["cost_per_person"] = float(cost_per_person)
            line["paying_pax"] = paying_pax
            line["range_label"] = pax_label  # group identifier
            lines.append(line)

    return lines


def _compute_per_person(
    entries: list, pax_configs: list,
    commission_pct: Decimal, vat_pct: Decimal, vat_mode: str,
    engine: QuotationEngine,
    secondary_commission_pct: Decimal = Decimal("0"),
) -> list:
    """Per person: single price × total pax.

    The user specifies total_pax and price_per_person.
    We use the entry's total_pax (not the pax_config's) for selling price calculation.
    Cost is extrapolated from the closest pax_config using cost_per_person.
    """
    lines = []
    for entry in entries:
        price_pp = Decimal(str(entry.get("price_per_person", 0)))
        total_pax = entry.get("total_pax", 2)

        pc = _find_pax_config(pax_configs, total_pax)
        if not pc:
            continue

        # Use entry's total_pax for selling price, not pax_config's paying_pax
        # The user chose how many people → the selling price reflects that
        selling_price_total = price_pp * total_pax

        # Cost: extrapolate from pax_config's cost_per_person × total_pax
        pc_total_pax = pc.get("total_pax", total_pax)
        total_cost_raw = Decimal(str(pc.get("total_cost", 0)))
        vat_surcharge = _get_vat_surcharge(pc)
        cost_no_surcharge = total_cost_raw - vat_surcharge
        cost_per_person = (cost_no_surcharge / pc_total_pax).quantize(Decimal("0.01")) if pc_total_pax > 0 else Decimal("0")
        total_cost = cost_per_person * total_pax

        # VAT recoverable: extrapolate proportionally
        vat_recov_raw = _get_vat_recoverable(pc)
        vat_recov = (vat_recov_raw * total_pax / pc_total_pax).quantize(Decimal("0.01")) if pc_total_pax > 0 else Decimal("0")

        line = _compute_margin_line(
            label=f"{total_pax} pers × {float(price_pp):.0f}",
            selling_price=selling_price_total,
            total_cost=total_cost,
            vat_recoverable_from_cotation=vat_recov,
            commission_pct=commission_pct,
            vat_pct=vat_pct,
            vat_mode=vat_mode,
            engine=engine,
            secondary_commission_pct=secondary_commission_pct,
        )
        line["price_per_person"] = float(price_pp)
        line["cost_per_person"] = float(cost_per_person)
        line["paying_pax"] = total_pax
        lines.append(line)

    return lines


def _compute_per_group(
    entries: list, pax_configs: list,
    commission_pct: Decimal, vat_pct: Decimal, vat_mode: str,
    engine: QuotationEngine,
    secondary_commission_pct: Decimal = Decimal("0"),
) -> list:
    """Per group: fixed total price for the group.

    The user specifies total_pax and group_price.
    Cost is extrapolated from the closest pax_config using cost_per_person.
    """
    lines = []
    for entry in entries:
        group_price = Decimal(str(entry.get("group_price", 0)))
        total_pax = entry.get("total_pax", 2)

        pc = _find_pax_config(pax_configs, total_pax)
        if not pc:
            continue

        # Extrapolate cost from pax_config's cost_per_person × total_pax
        pc_total_pax = pc.get("total_pax", total_pax)
        total_cost_raw = Decimal(str(pc.get("total_cost", 0)))
        vat_surcharge = _get_vat_surcharge(pc)
        cost_no_surcharge = total_cost_raw - vat_surcharge
        cost_per_person = (cost_no_surcharge / pc_total_pax).quantize(Decimal("0.01")) if pc_total_pax > 0 else Decimal("0")
        total_cost = cost_per_person * total_pax

        # VAT recoverable: extrapolate proportionally
        vat_recov_raw = _get_vat_recoverable(pc)
        vat_recov = (vat_recov_raw * total_pax / pc_total_pax).quantize(Decimal("0.01")) if pc_total_pax > 0 else Decimal("0")

        line = _compute_margin_line(
            label=f"Groupe de {total_pax}",
            selling_price=group_price,
            total_cost=total_cost,
            vat_recoverable_from_cotation=vat_recov,
            commission_pct=commission_pct,
            vat_pct=vat_pct,
            vat_mode=vat_mode,
            engine=engine,
            secondary_commission_pct=secondary_commission_pct,
        )
        line["price_per_person"] = float(
            (group_price / total_pax).quantize(Decimal("0.01"))
        ) if total_pax > 0 else 0
        line["cost_per_person"] = float(cost_per_person)
        line["paying_pax"] = total_pax
        lines.append(line)

    return lines


def _compute_service_list(
    entries: list, pax_configs: list,
    commission_pct: Decimal, vat_pct: Decimal, vat_mode: str,
    engine: QuotationEngine,
    secondary_commission_pct: Decimal = Decimal("0"),
) -> list:
    """Service list: different groups of people with their own pricing.

    Pax are CUMULATIVE: 2 pers (line 1) + 2 pers (line 2) = 4 pax total.
    Cost lookup uses the running cumulative pax count.
    """
    lines = []
    cumulative_pax = 0
    for entry in entries:
        label = entry.get("label", "Prestation")
        pax = entry.get("pax", 2)
        price_pp = Decimal(str(entry.get("price_per_person", 0)))
        explicit_cumulative = entry.get("cumulative_pax")

        selling_price_line = price_pp * pax
        cumulative_pax = explicit_cumulative or (cumulative_pax + pax)

        # Find cost for this pax count — use cumulative pax for cost lookup
        pc = _find_pax_config(pax_configs, cumulative_pax)
        if not pc:
            # Fallback: proportional cost
            any_pc = pax_configs[0] if pax_configs else None
            if any_pc:
                cost_pp = Decimal(str(any_pc.get("cost_per_person", 0)))
                vat_surcharge_pp = _get_vat_surcharge(any_pc) / any_pc.get("total_pax", 1) if any_pc.get("total_pax", 0) > 0 else Decimal("0")
                total_cost_line = (cost_pp - vat_surcharge_pp) * pax
            else:
                total_cost_line = Decimal("0")
            vat_recov = Decimal("0")
        else:
            # Proportional cost for this line's pax from total (without VAT surcharge)
            total_cost_full = Decimal(str(pc.get("total_cost", 0))) - _get_vat_surcharge(pc)
            paying_pax_full = pc.get("paying_pax", cumulative_pax)
            total_cost_line = (
                (total_cost_full * pax / paying_pax_full).quantize(Decimal("0.01"))
                if paying_pax_full > 0 else Decimal("0")
            )
            vat_recov = _get_vat_recoverable(pc)
            # Prorate VAT recoverable
            vat_recov = (vat_recov * pax / paying_pax_full).quantize(Decimal("0.01")) if paying_pax_full > 0 else Decimal("0")

        line = _compute_margin_line(
            label=label,
            selling_price=selling_price_line,
            total_cost=total_cost_line,
            vat_recoverable_from_cotation=vat_recov,
            commission_pct=commission_pct,
            vat_pct=vat_pct,
            vat_mode=vat_mode,
            engine=engine,
            secondary_commission_pct=secondary_commission_pct,
        )
        line["pax"] = pax
        line["price_per_person"] = float(price_pp)
        line["cost_per_person"] = float(
            (total_cost_line / pax).quantize(Decimal("0.01"))
        ) if pax > 0 else 0
        lines.append(line)

    return lines


def _compute_enumeration(
    entries: list, pax_configs: list,
    commission_pct: Decimal, vat_pct: Decimal, vat_mode: str,
    engine: QuotationEngine,
    secondary_commission_pct: Decimal = Decimal("0"),
) -> list:
    """Enumeration: detail of services for the SAME people.

    Unlike service_list, pax do NOT accumulate. The quantity on the first
    entry determines the pax count used for cost lookup across all lines.
    Each line is a different service for those same participants.
    """
    lines = []
    # The pax count is the quantity of the first entry (same people across all lines)
    reference_pax = entries[0].get("quantity", 1) if entries else 1

    for entry in entries:
        label = entry.get("label", "Prestation")
        unit_price = Decimal(str(entry.get("unit_price", 0)))
        quantity = entry.get("quantity", 1)

        selling_price_line = unit_price * quantity

        # Cost lookup uses reference_pax (same group for all lines)
        pc = _find_pax_config(pax_configs, reference_pax)
        if not pc:
            any_pc = pax_configs[0] if pax_configs else None
            if any_pc:
                cost_pp = Decimal(str(any_pc.get("cost_per_person", 0)))
                vat_surcharge_pp = _get_vat_surcharge(any_pc) / any_pc.get("total_pax", 1) if any_pc.get("total_pax", 0) > 0 else Decimal("0")
                total_cost_line = (cost_pp - vat_surcharge_pp) * quantity
            else:
                total_cost_line = Decimal("0")
            vat_recov = Decimal("0")
        else:
            total_cost_full = Decimal(str(pc.get("total_cost", 0))) - _get_vat_surcharge(pc)
            paying_pax_full = pc.get("paying_pax", reference_pax)
            total_cost_line = (
                (total_cost_full * quantity / paying_pax_full).quantize(Decimal("0.01"))
                if paying_pax_full > 0 else Decimal("0")
            )
            vat_recov = _get_vat_recoverable(pc)
            vat_recov = (vat_recov * quantity / paying_pax_full).quantize(Decimal("0.01")) if paying_pax_full > 0 else Decimal("0")

        line = _compute_margin_line(
            label=label,
            selling_price=selling_price_line,
            total_cost=total_cost_line,
            vat_recoverable_from_cotation=vat_recov,
            commission_pct=commission_pct,
            vat_pct=vat_pct,
            vat_mode=vat_mode,
            engine=engine,
            secondary_commission_pct=secondary_commission_pct,
        )
        line["unit_price"] = float(unit_price)
        line["quantity"] = quantity
        line["cost_per_person"] = float(
            (total_cost_line / quantity).quantize(Decimal("0.01"))
        ) if quantity > 0 else 0
        lines.append(line)

    return lines


def _compute_totals(lines: list) -> dict:
    """Aggregate totals from all lines."""
    if not lines:
        return {
            "label": "Total",
            "selling_price": 0, "total_cost": 0,
            "margin_total": 0, "margin_pct": 0,
            "primary_commission_amount": 0, "secondary_commission_amount": 0,
            "commission_amount": 0, "agency_selling_price": 0,
            "margin_after_commission": 0,
            "vat_forecast": 0, "vat_recoverable": 0, "net_vat": 0,
            "margin_nette": 0,
        }

    total_selling = sum(l["selling_price"] for l in lines)
    total_cost = sum(l["total_cost"] for l in lines)
    total_margin = sum(l["margin_total"] for l in lines)
    total_primary_commission = sum(l.get("primary_commission_amount", 0) for l in lines)
    total_secondary_commission = sum(l.get("secondary_commission_amount", 0) for l in lines)
    total_commission = sum(l["commission_amount"] for l in lines)
    total_agency_selling = sum(l.get("agency_selling_price", 0) for l in lines)
    total_margin_after = sum(l["margin_after_commission"] for l in lines)
    total_vat_forecast = sum(l["vat_forecast"] for l in lines)
    total_vat_recov = sum(l["vat_recoverable"] for l in lines)
    total_net_vat = sum(l["net_vat"] for l in lines)
    total_margin_nette = sum(l["margin_nette"] for l in lines)
    margin_pct = (total_margin / total_selling * 100) if total_selling > 0 else 0

    return {
        "label": "Total",
        "selling_price": round(total_selling, 2),
        "total_cost": round(total_cost, 2),
        "margin_total": round(total_margin, 2),
        "margin_pct": round(margin_pct, 2),
        "primary_commission_amount": round(total_primary_commission, 2),
        "secondary_commission_amount": round(total_secondary_commission, 2),
        "commission_amount": round(total_commission, 2),
        "agency_selling_price": round(total_agency_selling, 2),
        "margin_after_commission": round(total_margin_after, 2),
        "vat_forecast": round(total_vat_forecast, 2),
        "vat_recoverable": round(total_vat_recov, 2),
        "net_vat": round(total_net_vat, 2),
        "margin_nette": round(total_margin_nette, 2),
    }
