"""
Dossier management endpoints.
A Dossier represents a client travel inquiry that can have multiple Trip proposals.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.dossier import Dossier

router = APIRouter()


# Schemas
class DossierCreate(BaseModel):
    """Schema for creating a dossier."""
    reference: Optional[str] = None  # Auto-generated if not provided
    client_name: Optional[str] = None
    client_email: Optional[EmailStr] = None
    client_phone: Optional[str] = None
    client_company: Optional[str] = None
    client_address: Optional[str] = None
    departure_date_from: Optional[date] = None
    departure_date_to: Optional[date] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    budget_currency: str = "EUR"
    pax_adults: int = 2
    pax_children: int = 0
    pax_infants: int = 0
    destination_countries: Optional[List[str]] = None
    marketing_source: Optional[str] = None
    marketing_campaign: Optional[str] = None
    partner_agency_id: Optional[int] = None  # B2B partner agency
    internal_notes: Optional[str] = None
    is_hot: bool = False
    priority: int = 0
    assigned_to_id: Optional[uuid.UUID] = None


class DossierUpdate(BaseModel):
    """Schema for updating a dossier."""
    reference: Optional[str] = None
    status: Optional[str] = None
    client_name: Optional[str] = None
    client_email: Optional[EmailStr] = None
    client_phone: Optional[str] = None
    client_company: Optional[str] = None
    client_address: Optional[str] = None
    departure_date_from: Optional[date] = None
    departure_date_to: Optional[date] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    budget_currency: Optional[str] = None
    pax_adults: Optional[int] = None
    pax_children: Optional[int] = None
    pax_infants: Optional[int] = None
    destination_countries: Optional[List[str]] = None
    marketing_source: Optional[str] = None
    marketing_campaign: Optional[str] = None
    partner_agency_id: Optional[int] = None  # B2B partner agency
    internal_notes: Optional[str] = None
    lost_reason: Optional[str] = None
    lost_comment: Optional[str] = None
    is_hot: Optional[bool] = None
    priority: Optional[int] = None
    assigned_to_id: Optional[uuid.UUID] = None


class DossierSummaryResponse(BaseModel):
    """Summary response for listing dossiers."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    reference: str
    status: str
    client_name: Optional[str]
    client_email: Optional[str]
    departure_date_from: Optional[date]
    departure_date_to: Optional[date]
    destination_countries: Optional[List[str]]
    pax_adults: int
    pax_children: int
    pax_infants: int
    budget_min: Optional[float]
    budget_max: Optional[float]
    budget_currency: str
    partner_agency_id: Optional[int]
    is_hot: bool
    priority: int
    assigned_to_id: Optional[uuid.UUID]
    last_activity_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TripSummaryForDossier(BaseModel):
    """Trip summary when included in dossier response."""
    id: int
    name: str
    status: str
    start_date: Optional[date]
    duration_days: int

    class Config:
        from_attributes = True


class PartnerAgencySummary(BaseModel):
    """Partner agency summary for inclusion in dossier response."""
    id: int
    name: str
    code: Optional[str]
    logo_url: Optional[str]
    primary_color: Optional[str]

    class Config:
        from_attributes = True


class DossierResponse(BaseModel):
    """Full dossier response."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    reference: str
    status: str
    client_name: Optional[str]
    client_email: Optional[str]
    client_phone: Optional[str]
    client_company: Optional[str]
    client_address: Optional[str]
    departure_date_from: Optional[date]
    departure_date_to: Optional[date]
    budget_min: Optional[float]
    budget_max: Optional[float]
    budget_currency: str
    pax_adults: int
    pax_children: int
    pax_infants: int
    destination_countries: Optional[List[str]]
    marketing_source: Optional[str]
    marketing_campaign: Optional[str]
    partner_agency_id: Optional[int]
    partner_agency: Optional[PartnerAgencySummary] = None
    internal_notes: Optional[str]
    lost_reason: Optional[str]
    lost_comment: Optional[str]
    is_hot: bool
    priority: int
    created_by_id: Optional[uuid.UUID]
    assigned_to_id: Optional[uuid.UUID]
    last_activity_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    trips: List[TripSummaryForDossier] = []

    class Config:
        from_attributes = True


class DossierListResponse(BaseModel):
    """Paginated list response."""
    items: List[DossierSummaryResponse]
    total: int
    page: int
    page_size: int


# Helper functions
def _generate_dossier_reference(tenant_slug: str) -> str:
    """Generate a unique dossier reference."""
    from datetime import datetime
    import random
    import string
    timestamp = datetime.now().strftime("%y%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{tenant_slug.upper()[:3]}-{timestamp}-{random_part}"


# Endpoints
@router.get("", response_model=DossierListResponse)
async def list_dossiers(
    db: DbSession,
    tenant: CurrentTenant,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    is_hot: Optional[bool] = None,
    assigned_to_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
):
    """
    List dossiers for the current tenant.
    """
    query = select(Dossier).where(Dossier.tenant_id == tenant.id)

    # Filters
    if status:
        query = query.where(Dossier.status == status)
    if is_hot is not None:
        query = query.where(Dossier.is_hot == is_hot)
    if assigned_to_id:
        query = query.where(Dossier.assigned_to_id == assigned_to_id)
    if search:
        query = query.where(
            Dossier.client_name.ilike(f"%{search}%") |
            Dossier.client_email.ilike(f"%{search}%") |
            Dossier.reference.ilike(f"%{search}%")
        )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Pagination and ordering
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Dossier.is_hot.desc(), Dossier.updated_at.desc())

    result = await db.execute(query)
    dossiers = result.scalars().all()

    return DossierListResponse(
        items=[DossierSummaryResponse.model_validate(d) for d in dossiers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DossierResponse, status_code=status.HTTP_201_CREATED)
async def create_dossier(
    data: DossierCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new dossier.
    """
    # Generate reference if not provided
    reference = data.reference
    if not reference:
        reference = _generate_dossier_reference(tenant.slug or "DOS")

    dossier = Dossier(
        tenant_id=tenant.id,
        created_by_id=user.id,
        reference=reference,
        status="lead",
        last_activity_at=datetime.utcnow(),
        **data.model_dump(exclude={"reference"}),
    )
    db.add(dossier)
    await db.commit()

    # Reload with relations
    result = await db.execute(
        select(Dossier)
        .where(Dossier.id == dossier.id)
        .options(
            selectinload(Dossier.trips),
            selectinload(Dossier.partner_agency),
        )
    )
    dossier = result.scalar_one()

    return DossierResponse.model_validate(dossier)


@router.get("/{dossier_id}", response_model=DossierResponse)
async def get_dossier(
    dossier_id: uuid.UUID,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a dossier with its trips and partner agency.
    """
    result = await db.execute(
        select(Dossier)
        .where(Dossier.id == dossier_id, Dossier.tenant_id == tenant.id)
        .options(
            selectinload(Dossier.trips),
            selectinload(Dossier.partner_agency),
        )
    )
    dossier = result.scalar_one_or_none()

    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dossier not found",
        )

    return DossierResponse.model_validate(dossier)


@router.patch("/{dossier_id}", response_model=DossierResponse)
async def update_dossier(
    dossier_id: uuid.UUID,
    data: DossierUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a dossier.
    """
    result = await db.execute(
        select(Dossier)
        .where(Dossier.id == dossier_id, Dossier.tenant_id == tenant.id)
        .options(
            selectinload(Dossier.trips),
            selectinload(Dossier.partner_agency),
        )
    )
    dossier = result.scalar_one_or_none()

    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dossier not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dossier, field, value)

    # Update last activity
    dossier.last_activity_at = datetime.utcnow()

    await db.commit()

    # Reload with partner agency relation (in case it changed)
    result = await db.execute(
        select(Dossier)
        .where(Dossier.id == dossier.id)
        .options(
            selectinload(Dossier.trips),
            selectinload(Dossier.partner_agency),
        )
    )
    dossier = result.scalar_one()

    return DossierResponse.model_validate(dossier)


@router.delete("/{dossier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dossier(
    dossier_id: uuid.UUID,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a dossier and all its trips.
    """
    result = await db.execute(
        select(Dossier).where(Dossier.id == dossier_id, Dossier.tenant_id == tenant.id)
    )
    dossier = result.scalar_one_or_none()

    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dossier not found",
        )

    await db.delete(dossier)
    await db.commit()


@router.post("/{dossier_id}/mark-lost", response_model=DossierResponse)
async def mark_dossier_lost(
    dossier_id: uuid.UUID,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    reason: Optional[str] = None,
    comment: Optional[str] = None,
):
    """
    Mark a dossier as lost.
    """
    result = await db.execute(
        select(Dossier)
        .where(Dossier.id == dossier_id, Dossier.tenant_id == tenant.id)
        .options(selectinload(Dossier.trips))
    )
    dossier = result.scalar_one_or_none()

    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dossier not found",
        )

    dossier.status = "lost"
    dossier.lost_reason = reason
    dossier.lost_comment = comment
    dossier.last_activity_at = datetime.utcnow()

    await db.commit()
    await db.refresh(dossier)

    return DossierResponse.model_validate(dossier)


@router.get("/stats/summary")
async def get_dossier_stats(
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get dossier statistics for the tenant.
    """
    # Count by status
    status_counts = {}
    for status_val in ["lead", "quote_in_progress", "quote_sent", "negotiation",
                       "confirmed", "deposit_paid", "fully_paid", "in_trip",
                       "completed", "lost", "cancelled", "archived"]:
        result = await db.execute(
            select(func.count())
            .select_from(Dossier)
            .where(Dossier.tenant_id == tenant.id, Dossier.status == status_val)
        )
        status_counts[status_val] = result.scalar()

    # Hot leads count
    result = await db.execute(
        select(func.count())
        .select_from(Dossier)
        .where(Dossier.tenant_id == tenant.id, Dossier.is_hot == True)
    )
    hot_count = result.scalar()

    return {
        "by_status": status_counts,
        "hot_leads": hot_count,
        "total_active": sum(
            status_counts.get(s, 0)
            for s in ["lead", "quote_in_progress", "quote_sent", "negotiation"]
        ),
    }
