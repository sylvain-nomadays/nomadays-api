"""
Tenant management endpoints.
"""

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
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
    if user.role != "admin_nomadays":
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


# ─── Invoice Config (Company Info) ────────────────────────────────────────────

class InvoiceSenderInfoResponse(BaseModel):
    """Full invoice sender configuration — returned by GET."""
    # Identity
    company_name: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Legal
    siren: Optional[str] = None
    siret: Optional[str] = None
    rcs: Optional[str] = None
    vat_number: Optional[str] = None
    capital: Optional[str] = None

    # Tourism
    immatriculation: Optional[str] = None
    garantie: Optional[str] = None
    assurance_rcp: Optional[str] = None
    mediateur: Optional[str] = None

    # VAT (from tenant columns)
    vat_regime: Optional[str] = None
    vat_rate: Optional[float] = None
    vat_legal_mention: Optional[str] = None

    # CGV (conditions particulières de vente)
    cgv_html: Optional[str] = None

    # Bank
    bank_account_holder: Optional[str] = None
    bank_name: Optional[str] = None
    bank_bic: Optional[str] = None
    bank_iban: Optional[str] = None
    bank_address: Optional[str] = None


class InvoiceSenderInfoUpdate(BaseModel):
    """Partial update for invoice sender configuration."""
    # Identity
    company_name: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Legal
    siren: Optional[str] = None
    siret: Optional[str] = None
    rcs: Optional[str] = None
    vat_number: Optional[str] = None
    capital: Optional[str] = None

    # Tourism
    immatriculation: Optional[str] = None
    garantie: Optional[str] = None
    assurance_rcp: Optional[str] = None
    mediateur: Optional[str] = None

    # VAT (stored on tenant columns)
    vat_regime: Optional[str] = None
    vat_rate: Optional[float] = None
    vat_legal_mention: Optional[str] = None

    # CGV (conditions particulières de vente)
    cgv_html: Optional[str] = None

    # Bank
    bank_account_holder: Optional[str] = None
    bank_name: Optional[str] = None
    bank_bic: Optional[str] = None
    bank_iban: Optional[str] = None
    bank_address: Optional[str] = None


# Fields stored in JSONB invoice_sender_info
_SENDER_INFO_FIELDS = [
    "company_name", "address", "postal_code", "city", "country",
    "phone", "email", "website",
    "siren", "siret", "rcs", "vat_number", "capital",
    "immatriculation", "garantie", "assurance_rcp", "mediateur",
    "cgv_html",
    "bank_account_holder", "bank_name", "bank_bic", "bank_iban", "bank_address",
]

# Fields stored as dedicated columns on Tenant
_TENANT_COLUMN_FIELDS = ["vat_regime", "vat_rate", "vat_legal_mention"]


@router.get("/current/invoice-config", response_model=InvoiceSenderInfoResponse)
async def get_invoice_config(
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Get invoice sender configuration (company info shown on invoices).
    Admin and manager only.
    """
    if user.role not in ("admin_nomadays", "dmc_manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can view invoice config",
        )

    sender = tenant.invoice_sender_info or {}

    return InvoiceSenderInfoResponse(
        # From JSONB
        company_name=sender.get("company_name"),
        address=sender.get("address"),
        postal_code=sender.get("postal_code"),
        city=sender.get("city"),
        country=sender.get("country"),
        phone=sender.get("phone"),
        email=sender.get("email"),
        website=sender.get("website"),
        siren=sender.get("siren") or (tenant.siren if tenant.siren else None),
        siret=sender.get("siret"),
        rcs=sender.get("rcs"),
        vat_number=sender.get("vat_number"),
        capital=sender.get("capital"),
        immatriculation=sender.get("immatriculation"),
        garantie=sender.get("garantie"),
        assurance_rcp=sender.get("assurance_rcp"),
        mediateur=sender.get("mediateur"),
        # From tenant columns
        vat_regime=tenant.vat_regime,
        vat_rate=float(tenant.vat_rate) if tenant.vat_rate is not None else None,
        vat_legal_mention=tenant.vat_legal_mention,
        # CGV
        cgv_html=sender.get("cgv_html"),
        # Bank
        bank_account_holder=sender.get("bank_account_holder"),
        bank_name=sender.get("bank_name"),
        bank_bic=sender.get("bank_bic"),
        bank_iban=sender.get("bank_iban"),
        bank_address=sender.get("bank_address"),
    )


@router.patch("/current/invoice-config", response_model=InvoiceSenderInfoResponse)
async def update_invoice_config(
    update: InvoiceSenderInfoUpdate,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
):
    """
    Update invoice sender configuration (company info shown on invoices).
    Merges with existing data. Admin and manager only.
    """
    if user.role not in ("admin_nomadays", "dmc_manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can update invoice config",
        )

    update_data = update.model_dump(exclude_unset=True)

    # ---- Update JSONB sender_info (merge) ----
    sender = dict(tenant.invoice_sender_info or {})
    for field in _SENDER_INFO_FIELDS:
        if field in update_data:
            value = update_data[field]
            if value is not None:
                sender[field] = value
            else:
                sender.pop(field, None)  # Remove key if explicitly set to null
    tenant.invoice_sender_info = sender

    # Sync siren to dedicated column as well (réforme 2026)
    if "siren" in update_data and update_data["siren"]:
        tenant.siren = update_data["siren"]

    # ---- Update dedicated tenant columns ----
    for field in _TENANT_COLUMN_FIELDS:
        if field in update_data:
            value = update_data[field]
            if field == "vat_rate" and value is not None:
                value = Decimal(str(value))
            setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)

    # Return full config
    return await get_invoice_config(tenant, user)
