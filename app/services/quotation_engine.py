"""
Quotation Engine - Core business logic for calculating trip costs.

This engine implements the complex pricing rules:
- Ratio calculations (per pax category, per N pax, etc.)
- Temporal multipliers (service days, total, fixed)
- Seasonal pricing variations
- Multiple margin types (margin, markup, amount, quotation)
- Multi-currency conversion (THB, USD, CNY → EUR)
- Advanced VAT calculation (on_margin vs on_selling_price)
- Item-level VAT recovery for TTC purchases
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.item import Item, ItemPriceTier
    from app.models.formula import Formula
    from app.models.trip import Trip
    from app.models.country_vat_rate import CountryVatRate


class MissingExchangeRateError(Exception):
    """Raised when an exchange rate is missing for currency conversion."""

    def __init__(self, from_currency: str, to_currency: str):
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.message = f"Taux de change requis: {from_currency} → {to_currency}"
        super().__init__(self.message)


class QuotationEngine:
    """
    Calculates costs and prices for trip items.

    Supports:
    - Different ratio types (ratio vs set)
    - Pax category filtering (adult, teen, child, baby)
    - Temporal multipliers based on service days
    - Seasonal price variations
    - Multiple pricing/margin methods
    """

    def __init__(
        self,
        default_margin_pct: float = 30.0,
        margin_type: str = "margin",
        currency: str = "EUR",
        duration_days: int = 1,
        start_date: Optional[date] = None,
        paying_pax_categories: Optional[Set[str]] = None,
    ):
        self.default_margin_pct = Decimal(str(default_margin_pct))
        self.margin_type = margin_type
        self.currency = currency
        self.duration_days = duration_days
        self.start_date = start_date
        # Categories that count for price_per_person (excludes tour_leader)
        # If None, all categories count (backward compatible)
        self.paying_pax_categories = paying_pax_categories

    # Mapping CostNature codes → CountryVatRate categories
    COST_NATURE_VAT_CATEGORY = {
        "HTL": "hotel",
        "TRS": "transport",
        "ACT": "activity",
        "RES": "restaurant",
        "GDE": "standard",
        "MIS": "standard",
    }

    @staticmethod
    def _cost_nature_to_vat_category(code: str) -> str:
        """Map a CostNature code to a CountryVatRate category."""
        return QuotationEngine.COST_NATURE_VAT_CATEGORY.get(code, "standard")

    def _get_item_vat_rate(
        self,
        item: "Item",
        country_vat_rate: Optional["CountryVatRate"],
    ) -> Optional[float]:
        """
        Get applicable VAT rate for an item.

        Priority:
        1. Item-level explicit vat_rate override
        2. Country rate by cost nature category
        3. Country standard rate (fallback)
        """
        # 1. Item-level override
        explicit_rate = getattr(item, "vat_rate", None)
        if explicit_rate is not None:
            return float(explicit_rate)

        # 2. Country rate by cost nature category
        if country_vat_rate:
            cost_nature = getattr(item, "cost_nature", None)
            if cost_nature and hasattr(cost_nature, "code"):
                category = self._cost_nature_to_vat_category(cost_nature.code)
                return float(country_vat_rate.get_rate_for_category(category))
            return float(country_vat_rate.vat_rate_standard)

        return None

    def calculate_item(
        self,
        item: "Item",
        pax_args: Dict[str, int],
        total_pax: int,
        formula: "Formula",
        trip: "Trip",
        country_vat_rate: Optional["CountryVatRate"] = None,
    ) -> Dict[str, Any]:
        """
        Calculate cost for a single item with currency conversion.

        Returns dict with:
        - unit_cost_local: base cost in item's original currency
        - unit_cost: cost converted to trip's selling currency
        - quantity: calculated quantity based on rules
        - subtotal_cost_local: in original currency
        - subtotal_cost: in selling currency
        - item_currency: original currency of the item
        - exchange_rate: rate used for conversion (1.0 if same currency)
        - vat_recoverable: VAT amount recoverable if item is TTC
        - vat_surcharge: VAT surcharge applied on HT items (on_selling_price mode)
        - warnings: any calculation warnings
        """
        warnings = []

        # 1. Get unit cost in local currency (considering tiers, then seasons)
        unit_cost_local, category_costs = self._resolve_unit_cost_with_tiers(
            item, pax_args, total_pax, trip, warnings
        )
        item_currency = getattr(item, "currency", None) or "EUR"

        # 2. Handle VAT on cost
        vat_recoverable = Decimal("0.00")
        vat_surcharge = Decimal("0.00")

        # Determine if item is TTC (price includes VAT)
        is_ttc = getattr(item, "price_includes_vat", None)
        if is_ttc is None:
            # Fallback to cost_nature default
            cost_nature = getattr(item, "cost_nature", None)
            is_ttc = getattr(cost_nature, "vat_recoverable_default", False) if cost_nature else False

        vat_calculation_mode = getattr(trip, "vat_calculation_mode", "on_margin") or "on_margin"

        if is_ttc:
            # Item is TTC → extract recoverable VAT from cost
            vat_rate_pct = self._get_item_vat_rate(item, country_vat_rate)
            if vat_rate_pct and vat_rate_pct > 0:
                vat_rate = Decimal(str(vat_rate_pct))
                unit_cost_ht = unit_cost_local / (Decimal("1") + vat_rate / Decimal("100"))
                vat_recoverable = (unit_cost_local - unit_cost_ht).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                unit_cost_local = unit_cost_ht.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            # Item is HT → if on_selling_price mode, surcharge cost by VAT rate
            # to protect margin from non-recoverable VAT
            if vat_calculation_mode == "on_selling_price" and country_vat_rate:
                vat_rate_pct = self._get_item_vat_rate(item, country_vat_rate)
                if vat_rate_pct and vat_rate_pct > 0:
                    vat_rate = Decimal(str(vat_rate_pct))
                    vat_surcharge = (unit_cost_local * vat_rate / Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    unit_cost_local = unit_cost_local + vat_surcharge

        # 3. Convert to selling currency if different
        selling_currency = trip.default_currency or "EUR"
        if item_currency != selling_currency:
            exchange_rate = self._get_exchange_rate(item_currency, trip)
            unit_cost = (unit_cost_local * exchange_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            vat_recoverable = (vat_recoverable * exchange_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            vat_surcharge = (vat_surcharge * exchange_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            exchange_rate = Decimal("1.00")
            unit_cost = unit_cost_local

        # 4. Calculate quantity and subtotals
        if category_costs is not None:
            # Tiered pricing with category adjustments
            # Each category has its own adjusted cost
            # Apply temporal multiplier
            temporal_multiplier = self._get_temporal_multiplier(item, formula, trip)
            ratio_type = item.ratio_type or "ratio"
            ratio_per = item.ratio_per or 1

            # For 'set' type with category costs, the tier cost is a total (not per-person)
            if ratio_type == "set":
                quantity = Decimal(str(ratio_per * temporal_multiplier))
                subtotal_cost_local = unit_cost_local * quantity
                subtotal_cost = unit_cost * quantity
            else:
                # 'ratio' type: compute per-category costs
                subtotal_cost_local = Decimal("0")
                total_quantity = 0
                ratio_categories = item.ratio_categories or ""
                categories_list = [c.strip().lower() for c in ratio_categories.split(",") if c.strip()]

                for cat, count in pax_args.items():
                    if count <= 0:
                        continue
                    if categories_list and "all" not in categories_list and cat not in categories_list:
                        continue

                    import math
                    cat_qty = math.ceil(count / ratio_per)
                    cat_cost = category_costs.get(cat, unit_cost_local)
                    subtotal_cost_local += cat_cost * Decimal(str(cat_qty)) * Decimal(str(temporal_multiplier))
                    total_quantity += cat_qty * temporal_multiplier

                quantity = Decimal(str(total_quantity))
                # Convert subtotal to selling currency
                subtotal_cost = (subtotal_cost_local * exchange_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ) if item_currency != selling_currency else subtotal_cost_local

            total_vat_recoverable = vat_recoverable * quantity
            total_vat_surcharge = vat_surcharge * quantity
        else:
            # Standard calculation (no category adjustments)
            quantity = self._calculate_quantity(
                item=item,
                pax_args=pax_args,
                total_pax=total_pax,
                formula=formula,
                trip=trip,
                warnings=warnings,
            )

            # 5. Calculate subtotals
            subtotal_cost_local = unit_cost_local * quantity
            subtotal_cost = unit_cost * quantity
            total_vat_recoverable = vat_recoverable * quantity
            total_vat_surcharge = vat_surcharge * quantity

        return {
            "unit_cost_local": unit_cost_local,
            "unit_cost": unit_cost,
            "quantity": quantity,
            "subtotal_cost_local": subtotal_cost_local,
            "subtotal_cost": subtotal_cost,
            "item_currency": item_currency,
            "selling_currency": selling_currency,
            "exchange_rate": exchange_rate,
            "vat_recoverable": total_vat_recoverable,
            "vat_surcharge": total_vat_surcharge,
            "warnings": warnings,
        }

    def _get_unit_cost(
        self,
        item: "Item",
        trip: "Trip",
        warnings: List[str],
    ) -> Decimal:
        """
        Get the unit cost, considering seasonal variations.
        """
        base_cost = item.unit_cost or Decimal("0")

        # Check for seasonal pricing
        if trip.start_date and hasattr(item, "seasons") and item.seasons:
            for season in item.seasons:
                if self._date_in_season(trip.start_date, season):
                    # Apply seasonal multiplier or override
                    if season.cost_override is not None:
                        return season.cost_override
                    elif season.cost_multiplier is not None:
                        return base_cost * season.cost_multiplier

        return base_cost

    def _resolve_unit_cost_with_tiers(
        self,
        item: "Item",
        pax_args: Dict[str, int],
        total_pax: int,
        trip: "Trip",
        warnings: List[str],
    ) -> Tuple[Decimal, Optional[Dict[str, Decimal]]]:
        """
        Determine unit cost: use price tiers if defined, otherwise base unit_cost.

        Returns:
            (unit_cost, category_costs) where category_costs is a dict of
            {category: adjusted_cost} if tiers have adjustments, else None.
        """
        price_tiers = getattr(item, "price_tiers", None) or []
        if not price_tiers:
            # No tiers — use standard cost (with seasonal logic)
            return (self._get_unit_cost(item, trip, warnings), None)

        # Determine pax count for tier selection
        tier_categories_str = getattr(item, "tier_categories", None)
        if tier_categories_str:
            tier_cats = [c.strip().lower() for c in tier_categories_str.split(",") if c.strip()]
        else:
            # Fallback: use ratio_categories
            tier_cats = [c.strip().lower() for c in (item.ratio_categories or "").split(",") if c.strip()]

        if not tier_cats or "all" in tier_cats:
            tier_pax_count = total_pax
        else:
            tier_pax_count = sum(pax_args.get(cat, 0) for cat in tier_cats)

        # Find matching tier (sorted by pax_min)
        matching_tier = None
        for tier in price_tiers:
            if tier.pax_min <= tier_pax_count <= tier.pax_max:
                matching_tier = tier
                break

        if not matching_tier:
            warnings.append(
                f"Item '{item.name}': aucun palier trouvé pour {tier_pax_count} pax, "
                f"utilisation du prix de base"
            )
            return (self._get_unit_cost(item, trip, warnings), None)

        base_cost = Decimal(str(matching_tier.unit_cost))

        # Apply category adjustments if present
        adjustments = matching_tier.category_adjustments_json
        if adjustments:
            category_costs: Dict[str, Decimal] = {}
            for cat, count in pax_args.items():
                if count <= 0:
                    continue
                adj_pct = adjustments.get(cat, 0)  # % adjustment (-10 = -10%)
                adj_cost = base_cost * (Decimal("1") + Decimal(str(adj_pct)) / Decimal("100"))
                category_costs[cat] = adj_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return (base_cost, category_costs)

        return (base_cost, None)

    def _get_exchange_rate(
        self,
        from_currency: str,
        trip: "Trip",
    ) -> Decimal:
        """
        Get exchange rate from trip's currency_rates_json.

        Expected structure:
        {
            "rates": {
                "THB": {"rate": 0.0258, "source": "kantox", "locked_at": "2026-02-01"},
                "USD": {"rate": 0.92, "source": "manual"}
            },
            "base_currency": "EUR"
        }

        The rate represents: 1 from_currency = rate base_currency
        e.g., 1 THB = 0.0258 EUR
        """
        currency_rates = getattr(trip, "currency_rates_json", None) or {}
        rates = currency_rates.get("rates", {})

        rate_data = rates.get(from_currency)
        if not rate_data:
            raise MissingExchangeRateError(from_currency, trip.default_currency or "EUR")

        rate_value = rate_data.get("rate") if isinstance(rate_data, dict) else rate_data

        if rate_value is None:
            raise MissingExchangeRateError(from_currency, trip.default_currency or "EUR")

        return Decimal(str(rate_value))

    def _date_in_season(self, check_date: date, season) -> bool:
        """
        Check if a date falls within a season period.
        """
        if season.valid_from and check_date < season.valid_from:
            return False
        if season.valid_to and check_date > season.valid_to:
            return False
        return True

    def _calculate_quantity(
        self,
        item: "Item",
        pax_args: Dict[str, int],
        total_pax: int,
        formula: "Formula",
        trip: "Trip",
        warnings: List[str],
    ) -> Decimal:
        """
        Calculate quantity based on ratio rules.

        ratio_categories: which pax types this applies to (e.g., "adult,teen")
        ratio_per: how many pax per unit (e.g., 1 guide per 10 pax → ratio_per=10)
        ratio_type: "ratio" (calculate based on pax) or "set" (fixed quantity)
        times_type: temporal multiplier - "service_days", "total", or "fixed"
        times_value: value for fixed multiplier
        """
        # 1. Calculate base quantity from ratio
        base_qty = self._apply_ratio(item, pax_args, total_pax, warnings)

        # 2. Apply temporal multiplier
        temporal_multiplier = self._get_temporal_multiplier(item, formula, trip)
        quantity = base_qty * temporal_multiplier

        return Decimal(str(quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _apply_ratio(
        self,
        item: "Item",
        pax_args: Dict[str, int],
        total_pax: int,
        warnings: List[str],
    ) -> int:
        """
        Apply ratio rules to get base quantity.
        """
        ratio_type = item.ratio_type or "ratio"
        ratio_per = item.ratio_per or 1
        ratio_categories = item.ratio_categories or ""

        # Parse categories
        categories = [c.strip().lower() for c in ratio_categories.split(",") if c.strip()]

        # "set" type: fixed quantity regardless of pax
        if ratio_type == "set":
            return ratio_per

        # "ratio" type: calculate based on pax
        # Determine relevant pax count
        if not categories or "all" in categories:
            # Apply to all pax
            relevant_pax = total_pax
        else:
            # Sum only specified categories (dynamic — accepts any category code)
            relevant_pax = sum(
                pax_args.get(cat, 0) for cat in categories
            )

        if relevant_pax == 0:
            return 0

        # Calculate quantity: 1 unit per ratio_per pax (rounded up)
        if ratio_per <= 0:
            warnings.append(f"Item {item.name}: ratio_per must be > 0, defaulting to 1")
            ratio_per = 1

        # For ratio calculation: ceil(relevant_pax / ratio_per)
        import math
        quantity = math.ceil(relevant_pax / ratio_per)

        return quantity

    def _get_temporal_multiplier(
        self,
        item: "Item",
        formula: "Formula",
        trip: "Trip",
    ) -> int:
        """
        Get the temporal multiplier for the item.

        times_type:
        - "service_days": multiply by the formula's service days span
        - "total": multiply by trip's total duration
        - "fixed": use times_value directly
        """
        times_type = item.times_type or "fixed"
        times_value = item.times_value or 1

        if times_type == "fixed":
            return times_value

        if times_type == "total":
            return trip.duration_days

        if times_type == "service_days":
            # Calculate from formula's service day range
            start = formula.service_day_start or 1
            end = formula.service_day_end or start
            return max(1, end - start + 1)

        return 1

    @staticmethod
    def should_include_item(
        item: "Item",
        formula: "Formula",
        trip_conditions_map: Dict[int, Any],
    ) -> tuple[bool, Optional[str]]:
        """
        Check whether an item should be included based on conditions.

        Logic:
        1. Formula has no condition_id → all items unconditional → include
        2. Formula has condition_id but item has no condition_option_id → common item → include
        3. Formula has condition_id and item has condition_option_id:
           a. Condition not activated on trip → exclude
           b. Condition deactivated (toggle OFF) → exclude
           c. selected_option_id != item.condition_option_id → exclude
           d. Match → include

        Args:
            item: The item to check
            formula: The parent formula
            trip_conditions_map: Dict mapping condition_id → TripCondition

        Returns:
            (include, reason):
            - (True, None) if item should be included
            - (False, reason) if item should be excluded
        """
        condition_id = getattr(formula, "condition_id", None)
        condition_option_id = getattr(item, "condition_option_id", None)

        # 1. Formula without condition → all items unconditional
        if not condition_id:
            return True, None

        # 2. Item without condition_option_id → common cost, always included
        if not condition_option_id:
            return True, None

        # 3. Both set: check against trip's selected option
        trip_condition = trip_conditions_map.get(condition_id)
        if trip_condition is None:
            # Condition not activated on this trip → exclude
            return False, (
                f"Item '{item.name}' exclu "
                f"(condition non activée sur ce circuit)"
            )

        # Condition deactivated (toggle OFF) → exclude
        if not trip_condition.is_active:
            return False, (
                f"Item '{item.name}' exclu "
                f"(condition désactivée)"
            )

        # Check if selected option matches
        if trip_condition.selected_option_id != condition_option_id:
            condition_option = getattr(item, "condition_option", None)
            item_label = condition_option.label if condition_option else "?"
            selected_label = (
                trip_condition.selected_option.label
                if trip_condition.selected_option
                else "?"
            )
            return False, (
                f"Item '{item.name}' exclu "
                f"(option '{item_label}' ≠ sélection '{selected_label}')"
            )

        # Match! Include the item
        return True, None

    def apply_margin(
        self,
        cost: Decimal,
        margin_pct: float,
        pricing_method: str = "quotation",
        pricing_value: Optional[float] = None,
    ) -> Decimal:
        """
        Apply margin to get selling price.

        pricing_method:
        - "quotation": use default margin calculation
        - "margin": price = cost / (1 - margin_pct/100)
        - "markup": price = cost * (1 + markup_pct/100)
        - "amount": price = cost + fixed_amount
        - "fixed": price = fixed value (pricing_value)
        """
        margin = Decimal(str(margin_pct))
        cost = Decimal(str(cost))

        if pricing_method == "fixed" and pricing_value is not None:
            return Decimal(str(pricing_value))

        if pricing_method == "amount" and pricing_value is not None:
            return cost + Decimal(str(pricing_value))

        if pricing_method == "markup":
            # Markup: price = cost * (1 + markup%)
            markup = margin if pricing_value is None else Decimal(str(pricing_value))
            return (cost * (Decimal("1") + markup / Decimal("100"))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        # Default: margin calculation
        # Margin: price = cost / (1 - margin%)
        # This means if margin is 30%, price = cost / 0.7
        if margin >= Decimal("100"):
            # Prevent division by zero or negative
            margin = Decimal("99")

        divisor = Decimal("1") - (margin / Decimal("100"))
        if divisor <= 0:
            divisor = Decimal("0.01")

        return (cost / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def calculate_vat(self, price: Decimal, vat_pct: float) -> Decimal:
        """
        Calculate VAT amount (simple method, use calculate_vat_advanced for full calculation).
        """
        return (price * Decimal(str(vat_pct)) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def calculate_vat_advanced(
        self,
        total_cost: Decimal,
        total_price: Decimal,
        vat_pct: float,
        vat_calculation_mode: str = "on_margin",
        primary_commission_pct: float = 0.0,
        vat_recoverable: Decimal = Decimal("0.00"),
    ) -> Dict[str, Decimal]:
        """
        Calculate VAT with advanced modes for travel agencies.

        Args:
            total_cost: Total cost of services (HT, after currency conversion)
            total_price: Total selling price (before VAT)
            vat_pct: VAT rate to apply (e.g., 20.0 for 20%)
            vat_calculation_mode: "on_margin" or "on_selling_price"
            primary_commission_pct: Commission % (e.g., Nomadays 11.5%)
            vat_recoverable: VAT already paid on TTC purchases (to be deducted)

        Returns:
            Dict with:
            - margin: gross margin (price - cost)
            - vat_base: the amount on which VAT is calculated
            - vat_amount: VAT to pay
            - net_vat: VAT minus recoverable (what's actually owed)
            - price_ttc: final price including VAT
        """
        vat_rate = Decimal(str(vat_pct))
        commission_rate = Decimal(str(primary_commission_pct))

        # Calculate margin
        margin = total_price - total_cost

        if vat_calculation_mode == "on_margin":
            # TVA sur la marge : Base = Marge brute
            # This is the standard French regime for travel agencies
            vat_base = margin
        elif vat_calculation_mode == "on_selling_price":
            # TVA sur le prix de vente (moins commission)
            # Base = Prix de vente - Commission principale
            commission_amount = (total_price * commission_rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            vat_base = total_price - commission_amount
        else:
            # Default to on_margin
            vat_base = margin

        # Calculate VAT
        vat_amount = (vat_base * vat_rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Net VAT = VAT due - VAT recoverable from TTC purchases
        net_vat = (vat_amount - vat_recoverable).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if net_vat < Decimal("0"):
            net_vat = Decimal("0.00")

        # Final price TTC
        price_ttc = (total_price + net_vat).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "margin": margin.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "vat_base": vat_base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "vat_amount": vat_amount,
            "vat_recoverable": vat_recoverable,
            "net_vat": net_vat,
            "price_ttc": price_ttc,
        }

    def get_paying_pax(self, pax_args: Dict[str, int]) -> int:
        """
        Get number of paying pax (those who count for price_per_person).
        Excludes categories like tour_leader where counts_for_pricing=False.
        """
        if self.paying_pax_categories is None:
            # No paying filter set — all pax are paying (backward compatible)
            return sum(pax_args.values())

        return sum(
            count for cat, count in pax_args.items()
            if cat in self.paying_pax_categories
        )

    def calculate_operator_commission(
        self,
        price: Decimal,
        commission_pct: float,
    ) -> Decimal:
        """
        Calculate operator commission (for B2B scenarios).
        """
        return (price * Decimal(str(commission_pct)) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def calculate_commissions(
        self,
        price: Decimal,
        primary_commission_pct: float = 0.0,
        primary_commission_label: str = "",
        secondary_commission_pct: Optional[float] = None,
        secondary_commission_label: str = "",
    ) -> Dict[str, Any]:
        """
        Calculate all commissions on a price.

        Returns:
            Dict with commission breakdowns and net amount
        """
        result = {
            "gross_price": price,
            "primary_commission": Decimal("0.00"),
            "primary_commission_label": primary_commission_label,
            "secondary_commission": Decimal("0.00"),
            "secondary_commission_label": secondary_commission_label,
            "total_commissions": Decimal("0.00"),
            "net_price": price,
        }

        # Primary commission (e.g., Nomadays 11.5%)
        if primary_commission_pct and primary_commission_pct > 0:
            result["primary_commission"] = self.calculate_operator_commission(
                price, primary_commission_pct
            )

        # Secondary commission (optional, e.g., partner agency)
        if secondary_commission_pct and secondary_commission_pct > 0:
            result["secondary_commission"] = self.calculate_operator_commission(
                price, secondary_commission_pct
            )

        result["total_commissions"] = (
            result["primary_commission"] + result["secondary_commission"]
        )
        result["net_price"] = price - result["total_commissions"]

        return result
