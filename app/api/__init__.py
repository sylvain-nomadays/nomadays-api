"""
API routes package.
"""

from app.api import (
    auth,
    tenants,
    suppliers,
    contracts,
    trips,
    quotation,
    alerts,
    dashboard,
    formulas,
    dossiers,
    travel_themes,
    exchange_rates,
    trip_locations,
    country_templates,
    partner_agencies,
    distribution,
    import_circuit,
)

__all__ = [
    "auth",
    "tenants",
    "suppliers",
    "contracts",
    "trips",
    "quotation",
    "alerts",
    "dashboard",
    "formulas",
    "dossiers",
    "travel_themes",
    "exchange_rates",
    "trip_locations",
    "country_templates",
    "partner_agencies",
    "distribution",
    "import_circuit",
]
