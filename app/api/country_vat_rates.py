"""
Country VAT Rate management endpoints.

Configurable VAT/TVA rates per country per tenant.
Different rates can be set for different service categories
(hotel, restaurant, transport, activity).
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.country_vat_rate import CountryVatRate, DEFAULT_COUNTRY_VAT_RATES

router = APIRouter()


# ============ SCHEMAS ============

class CountryVatRateCreate(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    country_name: Optional[str] = None
    vat_rate_standard: float = 0.0
    vat_rate_hotel: Optional[float] = None
    vat_rate_restaurant: Optional[float] = None
    vat_rate_transport: Optional[float] = None
    vat_rate_activity: Optional[float] = None
    is_active: bool = True


class CountryVatRateUpdate(BaseModel):
    country_name: Optional[str] = None
    vat_rate_standard: Optional[float] = None
    vat_rate_hotel: Optional[float] = None
    vat_rate_restaurant: Optional[float] = None
    vat_rate_transport: Optional[float] = None
    vat_rate_activity: Optional[float] = None
    vat_calculation_mode: Optional[Literal["on_margin", "on_selling_price"]] = None
    is_active: Optional[bool] = None


class CountryVatRateResponse(BaseModel):
    id: int
    country_code: str
    country_name: Optional[str] = None
    vat_rate_standard: float
    vat_rate_hotel: Optional[float] = None
    vat_rate_restaurant: Optional[float] = None
    vat_rate_transport: Optional[float] = None
    vat_rate_activity: Optional[float] = None
    vat_calculation_mode: str = "on_margin"
    is_active: bool

    class Config:
        from_attributes = True


# ============ ENDPOINTS ============

@router.get("", response_model=List[CountryVatRateResponse])
async def list_country_vat_rates(
    db: DbSession,
    tenant: CurrentTenant,
):
    """List all VAT rates for the tenant, ordered by country_code."""
    result = await db.execute(
        select(CountryVatRate)
        .where(CountryVatRate.tenant_id == tenant.id)
        .order_by(CountryVatRate.country_code)
    )
    rates = result.scalars().all()
    return [CountryVatRateResponse.model_validate(r) for r in rates]


@router.post("", response_model=CountryVatRateResponse, status_code=status.HTTP_201_CREATED)
async def create_country_vat_rate(
    data: CountryVatRateCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Create a new VAT rate entry for a country."""
    # Normalize country_code to uppercase
    country_code = data.country_code.upper()

    # Check uniqueness for (tenant_id, country_code)
    existing = await db.execute(
        select(CountryVatRate).where(
            CountryVatRate.tenant_id == tenant.id,
            CountryVatRate.country_code == country_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A VAT rate entry for country '{country_code}' already exists",
        )

    rate = CountryVatRate(
        tenant_id=tenant.id,
        country_code=country_code,
        country_name=data.country_name,
        vat_rate_standard=data.vat_rate_standard,
        vat_rate_hotel=data.vat_rate_hotel,
        vat_rate_restaurant=data.vat_rate_restaurant,
        vat_rate_transport=data.vat_rate_transport,
        vat_rate_activity=data.vat_rate_activity,
        is_active=data.is_active,
    )
    db.add(rate)
    await db.commit()
    await db.refresh(rate)
    return CountryVatRateResponse.model_validate(rate)


@router.patch("/{rate_id}", response_model=CountryVatRateResponse)
async def update_country_vat_rate(
    rate_id: int,
    data: CountryVatRateUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update a VAT rate entry."""
    result = await db.execute(
        select(CountryVatRate).where(
            CountryVatRate.id == rate_id,
            CountryVatRate.tenant_id == tenant.id,
        )
    )
    rate = result.scalar_one_or_none()
    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VAT rate entry not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rate, field, value)

    await db.commit()
    await db.refresh(rate)
    return CountryVatRateResponse.model_validate(rate)


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_country_vat_rate(
    rate_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a VAT rate entry."""
    result = await db.execute(
        select(CountryVatRate).where(
            CountryVatRate.id == rate_id,
            CountryVatRate.tenant_id == tenant.id,
        )
    )
    rate = result.scalar_one_or_none()
    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VAT rate entry not found",
        )

    await db.delete(rate)
    await db.commit()


@router.post("/seed", response_model=List[CountryVatRateResponse], status_code=status.HTTP_201_CREATED)
async def seed_country_vat_rates(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Seed the default VAT rate for the tenant's destination country.
    Each tenant = one destination country (from tenant.country_code).
    Only creates the rate for that single country, skips if it already exists.
    """
    tenant_country = tenant.country_code
    if not tenant_country:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant has no country_code configured",
        )

    tenant_country = tenant_country.upper()

    # Check if rate already exists for this tenant's country
    existing = await db.execute(
        select(CountryVatRate).where(
            CountryVatRate.tenant_id == tenant.id,
            CountryVatRate.country_code == tenant_country,
        )
    )
    if existing.scalar_one_or_none():
        # Already seeded — return current rates
        result = await db.execute(
            select(CountryVatRate)
            .where(CountryVatRate.tenant_id == tenant.id)
            .order_by(CountryVatRate.country_code)
        )
        return [CountryVatRateResponse.model_validate(r) for r in result.scalars().all()]

    # Find default rate for this country
    rate_data = next(
        (r for r in DEFAULT_COUNTRY_VAT_RATES if r["country_code"] == tenant_country),
        None,
    )

    # Fallback: create a 0% rate if no default found
    if not rate_data:
        rate_data = {
            "country_code": tenant_country,
            "country_name": None,
            "vat_rate_standard": 0,
        }

    rate = CountryVatRate(
        tenant_id=tenant.id,
        country_code=rate_data["country_code"],
        country_name=rate_data.get("country_name"),
        vat_rate_standard=rate_data.get("vat_rate_standard", 0),
        vat_rate_hotel=rate_data.get("vat_rate_hotel"),
        vat_rate_restaurant=rate_data.get("vat_rate_restaurant"),
        vat_rate_transport=rate_data.get("vat_rate_transport"),
        vat_rate_activity=rate_data.get("vat_rate_activity"),
        is_active=True,
    )
    db.add(rate)
    await db.commit()
    await db.refresh(rate)

    return [CountryVatRateResponse.model_validate(rate)]
