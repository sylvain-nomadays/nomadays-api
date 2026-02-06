"""
Tenant management endpoints.
"""

from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, CurrentTenant, require_role
from app.models.tenant import Tenant

router = APIRouter()


# Schemas
class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    country_code: str
    default_currency: str
    is_active: bool

    class Config:
        from_attributes = True


class TenantSettingsResponse(BaseModel):
    id: int
    name: str
    slug: str
    country_code: str
    default_currency: str
    default_margin_pct: float
    default_margin_type: str
    ai_price_threshold_info_pct: float
    ai_price_threshold_critical_pct: float
    contract_alert_days_1: int
    contract_alert_days_2: int
    contract_alert_days_3: int
    pax_categories_json: list | None
    settings_json: dict | None

    class Config:
        from_attributes = True


# Endpoints
@router.get("/current", response_model=TenantSettingsResponse)
async def get_current_tenant_info(tenant: CurrentTenant):
    """
    Get current tenant information and settings.
    """
    return TenantSettingsResponse.model_validate(tenant)


@router.patch("/current/settings")
async def update_tenant_settings(
    settings_update: dict,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
):
    """
    Update tenant settings. Admin only.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update tenant settings",
        )

    # Update allowed fields
    allowed_fields = [
        "default_margin_pct",
        "default_margin_type",
        "ai_price_threshold_info_pct",
        "ai_price_threshold_critical_pct",
        "contract_alert_days_1",
        "contract_alert_days_2",
        "contract_alert_days_3",
        "pax_categories_json",
        "settings_json",
    ]

    for field, value in settings_update.items():
        if field in allowed_fields:
            setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)

    return TenantSettingsResponse.model_validate(tenant)
