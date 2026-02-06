"""
Partner Agencies API - B2B partner management with branding and templates.

Partners can have custom branding (logo, colors) and document templates
that are used when generating PDFs for their clients.
"""

from typing import List, Optional
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_current_user, get_tenant_id
from app.models.partner_agency import PartnerAgency

router = APIRouter(prefix="/partner-agencies", tags=["Partner Agencies"])


# ============================================================================
# Schemas
# ============================================================================

class TemplateContent(BaseModel):
    """Template content structure."""
    content: str
    variables: List[str] = []


class PartnerAgencyBranding(BaseModel):
    """Branding configuration for a partner."""
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    secondary_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    accent_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    font_family: Optional[str] = None
    pdf_style: str = "modern"
    pdf_header_html: Optional[str] = None
    pdf_footer_html: Optional[str] = None


class PartnerAgencyCreate(BaseModel):
    """Schema for creating a partner agency."""
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    is_active: bool = True

    # Contact
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None

    # Branding
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    pdf_style: str = "modern"
    pdf_header_html: Optional[str] = None
    pdf_footer_html: Optional[str] = None

    # Templates
    template_booking_conditions: Optional[dict] = None
    template_cancellation_policy: Optional[dict] = None
    template_general_info: Optional[dict] = None
    template_legal_mentions: Optional[dict] = None

    # Meta
    notes: Optional[str] = None
    sort_order: int = 0


class PartnerAgencyUpdate(BaseModel):
    """Schema for updating a partner agency."""
    name: Optional[str] = None
    code: Optional[str] = None
    is_active: Optional[bool] = None

    # Contact
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None

    # Branding
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    pdf_style: Optional[str] = None
    pdf_header_html: Optional[str] = None
    pdf_footer_html: Optional[str] = None

    # Templates
    template_booking_conditions: Optional[dict] = None
    template_cancellation_policy: Optional[dict] = None
    template_general_info: Optional[dict] = None
    template_legal_mentions: Optional[dict] = None

    # Meta
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class PartnerAgencyResponse(BaseModel):
    """Response schema for a partner agency."""
    id: int
    tenant_id: uuid.UUID  # UUID type for proper serialization
    name: str
    code: Optional[str]
    is_active: bool

    # Contact
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    website: Optional[str]
    address: Optional[str]

    # Branding
    logo_url: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    accent_color: Optional[str]
    font_family: Optional[str]
    pdf_style: str
    pdf_header_html: Optional[str]
    pdf_footer_html: Optional[str]

    # Templates
    template_booking_conditions: Optional[dict]
    template_cancellation_policy: Optional[dict]
    template_general_info: Optional[dict]
    template_legal_mentions: Optional[dict]

    # Meta
    notes: Optional[str]
    sort_order: int

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PartnerAgencyListResponse(BaseModel):
    """Response for list of partner agencies."""
    items: List[PartnerAgencyResponse]
    total: int


class PartnerAgencyTemplatesResponse(BaseModel):
    """Response with just the templates for a partner."""
    booking_conditions: Optional[str] = None
    cancellation_policy: Optional[str] = None
    general_info: Optional[str] = None
    legal_mentions: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=PartnerAgencyListResponse)
async def list_partner_agencies(
    include_inactive: bool = Query(False, description="Include inactive partners"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """List all partner agencies for the tenant."""
    query = select(PartnerAgency).where(PartnerAgency.tenant_id == tenant_id)

    if not include_inactive:
        query = query.where(PartnerAgency.is_active == True)

    query = query.order_by(PartnerAgency.sort_order, PartnerAgency.name)

    result = await db.execute(query)
    agencies = result.scalars().all()

    return PartnerAgencyListResponse(
        items=[PartnerAgencyResponse.model_validate(a) for a in agencies],
        total=len(agencies),
    )


@router.post("", response_model=PartnerAgencyResponse, status_code=201)
async def create_partner_agency(
    agency_data: PartnerAgencyCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Create a new partner agency."""
    # Check for duplicate code if provided
    if agency_data.code:
        result = await db.execute(
            select(PartnerAgency)
            .where(
                PartnerAgency.tenant_id == tenant_id,
                PartnerAgency.code == agency_data.code,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Partner agency with code '{agency_data.code}' already exists"
            )

    agency = PartnerAgency(
        tenant_id=tenant_id,
        **agency_data.model_dump(),
    )
    db.add(agency)
    await db.commit()
    await db.refresh(agency)
    return agency


@router.get("/{agency_id}", response_model=PartnerAgencyResponse)
async def get_partner_agency(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Get a specific partner agency."""
    result = await db.execute(
        select(PartnerAgency)
        .where(
            PartnerAgency.id == agency_id,
            PartnerAgency.tenant_id == tenant_id,
        )
    )
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(status_code=404, detail="Partner agency not found")
    return agency


@router.patch("/{agency_id}", response_model=PartnerAgencyResponse)
async def update_partner_agency(
    agency_id: int,
    agency_data: PartnerAgencyUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Update a partner agency."""
    result = await db.execute(
        select(PartnerAgency)
        .where(
            PartnerAgency.id == agency_id,
            PartnerAgency.tenant_id == tenant_id,
        )
    )
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(status_code=404, detail="Partner agency not found")

    # Check for duplicate code if changing
    if agency_data.code and agency_data.code != agency.code:
        result = await db.execute(
            select(PartnerAgency)
            .where(
                PartnerAgency.tenant_id == tenant_id,
                PartnerAgency.code == agency_data.code,
                PartnerAgency.id != agency_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Partner agency with code '{agency_data.code}' already exists"
            )

    for field, value in agency_data.model_dump(exclude_unset=True).items():
        setattr(agency, field, value)

    await db.commit()
    await db.refresh(agency)
    return agency


@router.delete("/{agency_id}", status_code=204)
async def delete_partner_agency(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Delete a partner agency."""
    result = await db.execute(
        select(PartnerAgency)
        .where(
            PartnerAgency.id == agency_id,
            PartnerAgency.tenant_id == tenant_id,
        )
    )
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(status_code=404, detail="Partner agency not found")

    await db.delete(agency)
    await db.commit()


@router.get("/{agency_id}/templates", response_model=PartnerAgencyTemplatesResponse)
async def get_partner_templates(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Get just the templates for a partner agency."""
    result = await db.execute(
        select(PartnerAgency)
        .where(
            PartnerAgency.id == agency_id,
            PartnerAgency.tenant_id == tenant_id,
        )
    )
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(status_code=404, detail="Partner agency not found")

    return PartnerAgencyTemplatesResponse(
        booking_conditions=agency.get_template("booking_conditions"),
        cancellation_policy=agency.get_template("cancellation_policy"),
        general_info=agency.get_template("general_info"),
        legal_mentions=agency.get_template("legal_mentions"),
    )


@router.get("/{agency_id}/branding", response_model=PartnerAgencyBranding)
async def get_partner_branding(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Get the branding configuration for a partner agency."""
    result = await db.execute(
        select(PartnerAgency)
        .where(
            PartnerAgency.id == agency_id,
            PartnerAgency.tenant_id == tenant_id,
        )
    )
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(status_code=404, detail="Partner agency not found")

    branding = agency.get_branding()
    return PartnerAgencyBranding(**branding)
