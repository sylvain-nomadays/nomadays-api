"""
Pax config auto-generator.

Generates pax configurations in two modes:
- Range mode: from min_pax to max_pax adults with smart business rules
- Custom mode: a single fixed composition (e.g. 2 adults + 1 child)
"""

import math
from typing import List, Dict, Any, Optional


# ─── All supported pax/room keys ─────────────────────────────────────────────
# Traveller categories
PAX_KEYS = ["adult", "teen", "child", "baby", "guide", "driver", "tour_leader", "cook"]
# Room/bed types
ROOM_KEYS = ["dbl", "sgl", "twn", "tpl", "fam", "exb", "cnt"]
# All keys combined
ALL_KEYS = PAX_KEYS + ROOM_KEYS

# Short labels for auto-generated config labels
_SHORT_LABELS = {
    "adult": "ad.",
    "teen": "ado.",
    "child": "enf.",
    "baby": "bb.",
    "guide": "gd.",
    "driver": "ch.",
    "tour_leader": "TL",
    "cook": "ck.",
}


def generate_pax_configs(min_pax: int = 2, max_pax: int = 10) -> List[Dict[str, Any]]:
    """
    Generate pax configurations from min_pax to max_pax adults (range mode).

    Rules:
    - guide: 1 per 10 total pax (always at least 1 for ≤ 10 pax)
    - driver: ceil((adults + guides) / 6) — 1 driver per 6 people in vehicle
    - DBL rooms: floor(adults / 2)
    - SGL rooms: adults % 2
    - total_pax: adults + guides + drivers

    Args:
        min_pax: minimum number of adults (default 2)
        max_pax: maximum number of adults (default 10)

    Returns:
        List of pax config dicts, each with:
        - label: "2 pax", "3 pax", ...
        - adult: number of adults
        - guide: number of guides
        - driver: number of drivers
        - dbl: number of double rooms
        - sgl: number of single rooms
        - total_pax: total people count
    """
    configs = []

    for adults in range(min_pax, max_pax + 1):
        guide_count = 1  # Always 1 guide for ≤ 10 pax
        if adults > 10:
            guide_count = math.ceil(adults / 10)

        total_in_vehicle = adults + guide_count
        driver_count = math.ceil(total_in_vehicle / 6)

        dbl_rooms = adults // 2
        sgl_rooms = adults % 2

        total_pax = adults + guide_count + driver_count

        configs.append({
            "label": f"{adults} pax",
            "adult": adults,
            "guide": guide_count,
            "driver": driver_count,
            "dbl": dbl_rooms,
            "sgl": sgl_rooms,
            "total_pax": total_pax,
        })

    return configs


def generate_custom_config(
    adult: int = 2,
    teen: int = 0,
    child: int = 0,
    baby: int = 0,
    guide: Optional[int] = None,
    driver: Optional[int] = None,
    tour_leader: int = 0,
    cook: int = 0,
    rooms: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Create a SINGLE pax config with the exact composition given (custom mode).

    Auto-calculates guide/driver if not provided. Auto-calculates rooms if not provided.

    Args:
        adult: number of adults (default 2)
        teen: number of teenagers 11-16 (default 0)
        child: number of children 2-10 (default 0)
        baby: number of babies 0-1 (default 0)
        guide: number of guides (None = auto-calculate)
        driver: number of drivers (None = auto-calculate)
        tour_leader: number of tour leaders (default 0)
        cook: number of cooks (default 0)
        rooms: optional room allocation override
               e.g. [{"bed_type": "FAM", "qty": 1}, {"bed_type": "SGL", "qty": 1}]
               If None, auto-calculate from adults (dbl + sgl)

    Returns:
        List with a single pax config dict
    """
    # Count total tourists (people needing transport/guide)
    total_tourists = adult + teen + child + baby

    # Auto-calculate guide if not specified
    if guide is None:
        if total_tourists <= 10:
            guide_count = 1
        else:
            guide_count = math.ceil(total_tourists / 10)
    else:
        guide_count = guide

    # Auto-calculate driver if not specified
    if driver is None:
        total_in_vehicle = total_tourists + guide_count + tour_leader + cook
        driver_count = math.ceil(total_in_vehicle / 6)
    else:
        driver_count = driver

    # Room allocation
    if rooms:
        # Use provided room allocation
        room_counts: Dict[str, int] = {}
        for room_entry in rooms:
            bed_type = room_entry.get("bed_type", "").lower()
            qty = room_entry.get("qty", 0)
            if bed_type and qty > 0:
                room_counts[bed_type] = qty
    else:
        # Auto-calculate: only from adults (children/babies share rooms)
        room_counts = {}
        dbl = adult // 2
        sgl = adult % 2
        if dbl > 0:
            room_counts["dbl"] = dbl
        if sgl > 0:
            room_counts["sgl"] = sgl

    # Total pax (all people)
    total_pax = (
        adult + teen + child + baby
        + guide_count + driver_count
        + tour_leader + cook
    )

    # Build label dynamically
    label = _build_custom_label(adult, teen, child, baby)

    # Build the config dict
    config: Dict[str, Any] = {
        "label": label,
        "adult": adult,
        "guide": guide_count,
        "driver": driver_count,
        "total_pax": total_pax,
    }

    # Add optional traveller categories only if > 0
    if teen > 0:
        config["teen"] = teen
    if child > 0:
        config["child"] = child
    if baby > 0:
        config["baby"] = baby
    if tour_leader > 0:
        config["tour_leader"] = tour_leader
    if cook > 0:
        config["cook"] = cook

    # Add room counts (always include dbl/sgl for consistency, others only if > 0)
    config["dbl"] = room_counts.get("dbl", 0)
    config["sgl"] = room_counts.get("sgl", 0)
    for room_key in ["twn", "tpl", "fam", "exb", "cnt"]:
        if room_counts.get(room_key, 0) > 0:
            config[room_key] = room_counts[room_key]

    return [config]


def _build_custom_label(adult: int, teen: int, child: int, baby: int) -> str:
    """Build a human-readable label for a custom pax composition."""
    parts = []
    if adult > 0:
        parts.append(f"{adult} ad.")
    if teen > 0:
        parts.append(f"{teen} ado.")
    if child > 0:
        parts.append(f"{child} enf.")
    if baby > 0:
        parts.append(f"{baby} bb.")

    if not parts:
        return "0 pax"

    return " + ".join(parts)


def build_pax_args(config: Dict[str, Any]) -> Dict[str, int]:
    """
    Build pax_args dict from a pax config for the QuotationEngine.

    Converts the config dict to the format expected by QuotationEngine.calculate_item():
    {"adult": N, "guide": N, "driver": N, "dbl": N, "sgl": N, "teen": N, ...}

    Includes all keys present in the config (not just the basic 5).

    Args:
        config: a single pax config dict from generate_pax_configs() or generate_custom_config()

    Returns:
        Dict mapping category codes to counts
    """
    args: Dict[str, int] = {}
    for key in ALL_KEYS:
        value = config.get(key, 0)
        if value > 0:
            args[key] = value
    # Always include adult even if 0 (shouldn't happen but for safety)
    if "adult" not in args:
        args["adult"] = 0
    return args


def format_args_label(config: Dict[str, Any]) -> str:
    """
    Format a pax config into a human-readable args string.

    Example: {"adult": 4, "guide": 1, "driver": 1, "dbl": 2} → "adult-4, guide-1, driver-1, dbl-2"
    """
    parts = []
    for key in ALL_KEYS:
        value = config.get(key, 0)
        if value > 0:
            parts.append(f"{key}-{value}")
    return ", ".join(parts)
