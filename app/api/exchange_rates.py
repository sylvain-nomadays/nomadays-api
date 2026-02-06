"""
Exchange Rate API endpoints.
Supports manual rates and Kantox integration for forward currency purchases.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import Trip

router = APIRouter()


# Schemas
class ExchangeRateEntry(BaseModel):
    """Single exchange rate entry."""
    rate: float = Field(..., gt=0, description="Exchange rate (1 source = rate target)")
    source: str = Field(default="manual", description="Rate source: manual or kantox")
    locked_at: Optional[datetime] = None
    kantox_reference: Optional[str] = None


class CurrencyRatesData(BaseModel):
    """Full currency rates structure for a trip."""
    rates: Dict[str, ExchangeRateEntry] = Field(default_factory=dict)
    base_currency: str = Field(default="EUR", description="Target/selling currency")
    kantox_reference: Optional[str] = None


class SetManualRateRequest(BaseModel):
    """Request to set a manual exchange rate."""
    from_currency: str = Field(..., min_length=3, max_length=3, description="Source currency code (e.g., THB)")
    rate: float = Field(..., gt=0, description="Exchange rate (1 source = rate target)")


class SetManualRatesRequest(BaseModel):
    """Request to set multiple manual exchange rates."""
    rates: Dict[str, float] = Field(..., description="Currency codes to rates mapping")


class LockRatesRequest(BaseModel):
    """Request to lock current rates for a trip."""
    lock_all: bool = Field(default=True, description="Lock all current rates")
    currencies: Optional[List[str]] = Field(default=None, description="Specific currencies to lock")


class ExchangeRateResponse(BaseModel):
    """Exchange rate response."""
    from_currency: str
    to_currency: str
    rate: float
    source: str
    locked_at: Optional[datetime]


class TripRatesResponse(BaseModel):
    """Response with all trip rates."""
    trip_id: int
    base_currency: str
    rates: Dict[str, ExchangeRateEntry]
    missing_currencies: List[str] = Field(default_factory=list)


# Helper to get trip with validation
async def _get_trip(db: DbSession, trip_id: int, tenant_id) -> Trip:
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant_id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    return trip


# Endpoints
@router.get("/trips/{trip_id}", response_model=TripRatesResponse)
async def get_trip_rates(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get all exchange rates configured for a trip.
    Also returns list of currencies used in items that don't have rates.
    """
    trip = await _get_trip(db, trip_id, tenant.id)

    currency_rates = trip.currency_rates_json or {}
    rates_data = currency_rates.get("rates", {})

    # Convert to response format
    rates = {}
    for currency, data in rates_data.items():
        if isinstance(data, dict):
            rates[currency] = ExchangeRateEntry(
                rate=data.get("rate", 1.0),
                source=data.get("source", "manual"),
                locked_at=data.get("locked_at"),
                kantox_reference=data.get("kantox_reference"),
            )
        else:
            # Legacy format: just the rate value
            rates[currency] = ExchangeRateEntry(rate=float(data), source="manual")

    # TODO: Scan items to find missing currencies
    # For now, return empty list
    missing_currencies = []

    return TripRatesResponse(
        trip_id=trip_id,
        base_currency=trip.default_currency or "EUR",
        rates=rates,
        missing_currencies=missing_currencies,
    )


@router.post("/trips/{trip_id}/manual", response_model=TripRatesResponse)
async def set_manual_rate(
    trip_id: int,
    data: SetManualRateRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Set a manual exchange rate for a trip.
    """
    trip = await _get_trip(db, trip_id, tenant.id)

    # Get or initialize currency_rates_json
    currency_rates = trip.currency_rates_json or {"rates": {}, "base_currency": trip.default_currency or "EUR"}
    if "rates" not in currency_rates:
        currency_rates["rates"] = {}

    # Set the rate
    currency_rates["rates"][data.from_currency.upper()] = {
        "rate": data.rate,
        "source": "manual",
        "locked_at": None,
    }

    trip.currency_rates_json = currency_rates
    await db.commit()
    await db.refresh(trip)

    return await get_trip_rates(trip_id, db, tenant)


@router.post("/trips/{trip_id}/manual-batch", response_model=TripRatesResponse)
async def set_manual_rates_batch(
    trip_id: int,
    data: SetManualRatesRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Set multiple manual exchange rates at once.
    """
    trip = await _get_trip(db, trip_id, tenant.id)

    currency_rates = trip.currency_rates_json or {"rates": {}, "base_currency": trip.default_currency or "EUR"}
    if "rates" not in currency_rates:
        currency_rates["rates"] = {}

    for currency, rate in data.rates.items():
        currency_rates["rates"][currency.upper()] = {
            "rate": rate,
            "source": "manual",
            "locked_at": None,
        }

    trip.currency_rates_json = currency_rates
    await db.commit()
    await db.refresh(trip)

    return await get_trip_rates(trip_id, db, tenant)


@router.post("/trips/{trip_id}/lock", response_model=TripRatesResponse)
async def lock_rates(
    trip_id: int,
    data: LockRatesRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Lock exchange rates for a trip (mark with timestamp).
    This is typically done before sending a quote to the client.
    """
    trip = await _get_trip(db, trip_id, tenant.id)

    currency_rates = trip.currency_rates_json or {"rates": {}}
    rates = currency_rates.get("rates", {})
    lock_time = datetime.utcnow().isoformat()

    currencies_to_lock = data.currencies if data.currencies else list(rates.keys())

    for currency in currencies_to_lock:
        if currency in rates:
            if isinstance(rates[currency], dict):
                rates[currency]["locked_at"] = lock_time
            else:
                rates[currency] = {
                    "rate": rates[currency],
                    "source": "manual",
                    "locked_at": lock_time,
                }

    currency_rates["rates"] = rates
    trip.currency_rates_json = currency_rates
    await db.commit()
    await db.refresh(trip)

    return await get_trip_rates(trip_id, db, tenant)


@router.delete("/trips/{trip_id}/{currency}", response_model=TripRatesResponse)
async def delete_rate(
    trip_id: int,
    currency: str,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Remove an exchange rate from a trip.
    """
    trip = await _get_trip(db, trip_id, tenant.id)

    currency_rates = trip.currency_rates_json or {"rates": {}}
    rates = currency_rates.get("rates", {})

    if currency.upper() in rates:
        del rates[currency.upper()]
        currency_rates["rates"] = rates
        trip.currency_rates_json = currency_rates
        await db.commit()
        await db.refresh(trip)

    return await get_trip_rates(trip_id, db, tenant)


# Kantox integration endpoints (stub for now)
@router.get("/kantox/live")
async def get_kantox_live_rate(
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(default="EUR", min_length=3, max_length=3),
    tenant: CurrentTenant = None,
):
    """
    Get live spot rate from Kantox.

    NOTE: This is a stub. Actual Kantox integration requires:
    - API credentials in tenant settings
    - Implementation of KantoxClient
    """
    # Check if Kantox is configured for this tenant
    tenant_settings = tenant.settings or {}
    kantox_config = tenant_settings.get("kantox", {})

    if not kantox_config.get("enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kantox integration not enabled for this tenant. Configure in tenant settings.",
        )

    # TODO: Implement actual Kantox API call
    # For now, return a stub response
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Kantox live rate fetching not yet implemented. Use manual rates for now.",
    )


@router.get("/kantox/forward")
async def get_kantox_forward_rate(
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(default="EUR", min_length=3, max_length=3),
    value_date: date = Query(..., description="Forward contract value date"),
    tenant: CurrentTenant = None,
):
    """
    Get forward rate from Kantox for a specific value date.

    NOTE: This is a stub. Actual Kantox integration requires:
    - API credentials in tenant settings
    - Implementation of KantoxClient
    """
    tenant_settings = tenant.settings or {}
    kantox_config = tenant_settings.get("kantox", {})

    if not kantox_config.get("enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kantox integration not enabled for this tenant. Configure in tenant settings.",
        )

    # TODO: Implement actual Kantox API call
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Kantox forward rate fetching not yet implemented. Use manual rates for now.",
    )


@router.post("/trips/{trip_id}/fetch-kantox", response_model=TripRatesResponse)
async def fetch_kantox_rates(
    trip_id: int,
    currencies: List[str] = Query(..., description="Currencies to fetch rates for"),
    db: DbSession = None,
    tenant: CurrentTenant = None,
    user: CurrentUser = None,
):
    """
    Fetch rates from Kantox and apply to trip.

    NOTE: This is a stub. Will use live rates when Kantox integration is complete.
    """
    tenant_settings = tenant.settings or {}
    kantox_config = tenant_settings.get("kantox", {})

    if not kantox_config.get("enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kantox integration not enabled for this tenant. Configure in tenant settings.",
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Kantox rate fetching not yet implemented. Use manual rates for now.",
    )
