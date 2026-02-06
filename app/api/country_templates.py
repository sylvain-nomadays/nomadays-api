"""
Country Templates API - Default templates for inclusions, exclusions, etc.

Templates can be:
- Global (country_code = NULL): Applies to all countries
- Country-specific: Overrides global template for that country
"""

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_current_user, get_tenant_id
from app.models.country_template import (
    CountryTemplate,
    DEFAULT_INCLUSIONS,
    DEFAULT_EXCLUSIONS,
    FORMALITIES_BY_COUNTRY,
)

router = APIRouter(prefix="/templates", tags=["Country Templates"])


# ============================================================================
# Schemas
# ============================================================================

class InclusionExclusionItem(BaseModel):
    """A single inclusion or exclusion item."""
    text: str = Field(..., min_length=1)
    default: bool = True


class TemplateContent(BaseModel):
    """Content for a text-based template."""
    content: str
    variables: List[str] = []


class CountryTemplateCreate(BaseModel):
    """Schema for creating a country template."""
    country_code: Optional[str] = Field(None, max_length=2, description="ISO country code, or NULL for global")
    country_name: Optional[str] = None
    template_type: str = Field(..., description="inclusions, exclusions, formalities, booking_conditions, cancellation_policy, general_info")
    content: dict = Field(..., description="Template content (structure depends on type)")
    is_active: bool = True
    sort_order: int = 0


class CountryTemplateUpdate(BaseModel):
    """Schema for updating a country template."""
    country_name: Optional[str] = None
    content: Optional[dict] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CountryTemplateResponse(BaseModel):
    """Response schema for a country template."""
    id: int
    country_code: Optional[str]
    country_name: Optional[str]
    template_type: str
    content: dict
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class TemplatesForCountryResponse(BaseModel):
    """All templates for a specific country."""
    country_code: Optional[str]
    inclusions: Optional[List[InclusionExclusionItem]] = None
    exclusions: Optional[List[InclusionExclusionItem]] = None
    formalities: Optional[str] = None
    booking_conditions: Optional[str] = None
    cancellation_policy: Optional[str] = None
    general_info: Optional[str] = None


# ============================================================================
# Template CRUD Endpoints
# ============================================================================

@router.get("", response_model=List[CountryTemplateResponse])
async def list_templates(
    template_type: Optional[str] = Query(None, description="Filter by type"),
    country_code: Optional[str] = Query(None, description="Filter by country (use 'global' for NULL)"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """List all templates for the tenant."""
    query = select(CountryTemplate).where(CountryTemplate.tenant_id == tenant_id)

    if template_type:
        query = query.where(CountryTemplate.template_type == template_type)

    if country_code:
        if country_code.lower() == "global":
            query = query.where(CountryTemplate.country_code.is_(None))
        else:
            query = query.where(CountryTemplate.country_code == country_code.upper())

    query = query.order_by(
        CountryTemplate.template_type,
        CountryTemplate.country_code.is_(None),  # Global last
        CountryTemplate.sort_order,
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/for-country/{country_code}", response_model=TemplatesForCountryResponse)
async def get_templates_for_country(
    country_code: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """
    Get all templates for a specific country.

    Falls back to global templates if country-specific not found.
    """
    country_code_upper = country_code.upper()

    # Get all templates (both country-specific and global)
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.tenant_id == tenant_id,
            CountryTemplate.is_active == True,
            or_(
                CountryTemplate.country_code == country_code_upper,
                CountryTemplate.country_code.is_(None),
            ),
        )
        .order_by(
            CountryTemplate.template_type,
            CountryTemplate.country_code.is_(None),  # Country-specific first
        )
    )
    templates = result.scalars().all()

    # Group by type, preferring country-specific over global
    by_type = {}
    for template in templates:
        if template.template_type not in by_type:
            by_type[template.template_type] = template

    # Build response
    response = TemplatesForCountryResponse(country_code=country_code_upper)

    if "inclusions" in by_type:
        response.inclusions = [
            InclusionExclusionItem(**item)
            for item in by_type["inclusions"].content
        ]

    if "exclusions" in by_type:
        response.exclusions = [
            InclusionExclusionItem(**item)
            for item in by_type["exclusions"].content
        ]

    if "formalities" in by_type:
        content = by_type["formalities"].content
        response.formalities = content.get("content", "") if isinstance(content, dict) else str(content)

    if "booking_conditions" in by_type:
        content = by_type["booking_conditions"].content
        response.booking_conditions = content.get("content", "") if isinstance(content, dict) else str(content)

    if "cancellation_policy" in by_type:
        content = by_type["cancellation_policy"].content
        response.cancellation_policy = content.get("content", "") if isinstance(content, dict) else str(content)

    if "general_info" in by_type:
        content = by_type["general_info"].content
        response.general_info = content.get("content", "") if isinstance(content, dict) else str(content)

    return response


@router.post("", response_model=CountryTemplateResponse, status_code=201)
async def create_template(
    template_data: CountryTemplateCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Create a new country template."""
    # Check for duplicate
    country_code = template_data.country_code.upper() if template_data.country_code else None
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.tenant_id == tenant_id,
            CountryTemplate.country_code == country_code if country_code else CountryTemplate.country_code.is_(None),
            CountryTemplate.template_type == template_data.template_type,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Template already exists for type '{template_data.template_type}' and country '{country_code or 'GLOBAL'}'"
        )

    template = CountryTemplate(
        tenant_id=tenant_id,
        country_code=country_code,
        country_name=template_data.country_name,
        template_type=template_data.template_type,
        content=template_data.content,
        is_active=template_data.is_active,
        sort_order=template_data.sort_order,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/{template_id}", response_model=CountryTemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Get a specific template."""
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.id == template_id,
            CountryTemplate.tenant_id == tenant_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.patch("/{template_id}", response_model=CountryTemplateResponse)
async def update_template(
    template_id: int,
    template_data: CountryTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Update a template."""
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.id == template_id,
            CountryTemplate.tenant_id == tenant_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in template_data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Delete a template."""
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.id == template_id,
            CountryTemplate.tenant_id == tenant_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    await db.commit()


# ============================================================================
# Seed Default Templates
# ============================================================================

@router.post("/seed-defaults", response_model=dict)
async def seed_default_templates(
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """
    Seed default templates for the tenant.

    Creates:
    - Global inclusions and exclusions
    - Country-specific formalities for common destinations
    """
    created_count = 0

    # Check if global inclusions exist
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.tenant_id == tenant_id,
            CountryTemplate.country_code.is_(None),
            CountryTemplate.template_type == "inclusions",
        )
    )
    if not result.scalar_one_or_none():
        db.add(CountryTemplate(
            tenant_id=tenant_id,
            country_code=None,
            template_type="inclusions",
            content=DEFAULT_INCLUSIONS,
            is_active=True,
        ))
        created_count += 1

    # Check if global exclusions exist
    result = await db.execute(
        select(CountryTemplate)
        .where(
            CountryTemplate.tenant_id == tenant_id,
            CountryTemplate.country_code.is_(None),
            CountryTemplate.template_type == "exclusions",
        )
    )
    if not result.scalar_one_or_none():
        db.add(CountryTemplate(
            tenant_id=tenant_id,
            country_code=None,
            template_type="exclusions",
            content=DEFAULT_EXCLUSIONS,
            is_active=True,
        ))
        created_count += 1

    # Add country-specific formalities
    for country_code, formalities_content in FORMALITIES_BY_COUNTRY.items():
        result = await db.execute(
            select(CountryTemplate)
            .where(
                CountryTemplate.tenant_id == tenant_id,
                CountryTemplate.country_code == country_code,
                CountryTemplate.template_type == "formalities",
            )
        )
        if not result.scalar_one_or_none():
            db.add(CountryTemplate(
                tenant_id=tenant_id,
                country_code=country_code,
                template_type="formalities",
                content={"content": formalities_content},
                is_active=True,
            ))
            created_count += 1

    await db.commit()

    return {
        "message": f"Created {created_count} default templates",
        "created_count": created_count,
    }
