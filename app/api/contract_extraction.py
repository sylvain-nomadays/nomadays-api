"""
Contract Rate Extraction API - Extract rates from PDF contracts using AI.
"""

from typing import Optional, List, Union
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel, field_validator

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.services.ai_extraction import get_extraction_service

router = APIRouter()


# ============================================================================
# Helper functions
# ============================================================================

def _build_full_date(mm_dd: Optional[str], year: Optional[str], is_end_date: bool = False) -> Optional[str]:
    """
    Convert MM-DD + year to YYYY-MM-DD format.

    Args:
        mm_dd: Date in MM-DD format (e.g., "11-01" for Nov 1st)
        year: Year string, can be "2025" or "2025-2026"
        is_end_date: If True and year is a range, use the last year

    Returns:
        Date in YYYY-MM-DD format, or original mm_dd if conversion not possible
    """
    if not mm_dd:
        return mm_dd

    # If already in YYYY-MM-DD format, return as-is
    if len(mm_dd) == 10 and mm_dd[4] == '-':
        return mm_dd

    # If no year provided, keep MM-DD format (recurring season)
    if not year:
        return mm_dd

    # Parse year (can be "2025" or "2025-2026")
    year_parts = year.split('-')

    # For start_date, use first year
    # For end_date with range like "2025-2026", use last year
    if is_end_date and len(year_parts) > 1:
        target_year = year_parts[-1]
    else:
        target_year = year_parts[0]

    # Validate MM-DD format
    if len(mm_dd) == 5 and mm_dd[2] == '-':
        return f"{target_year}-{mm_dd}"

    return mm_dd


# ============================================================================
# Response schemas
# ============================================================================

class ExtractedRoomCategoryResponse(BaseModel):
    """Extracted room category."""
    name: str
    code: Optional[str] = None
    max_occupancy: Optional[int] = None
    max_adults: Optional[int] = None
    max_children: Optional[int] = None
    available_bed_types: Optional[List[str]] = None
    description: Optional[str] = None


class ExtractedSeasonResponse(BaseModel):
    """Extracted season."""
    name: str
    code: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    year: Optional[str] = None  # Accept string like "2024-2025" or just year
    season_level: Optional[str] = "high"  # low, high, peak
    original_name: Optional[str] = None  # Original name from the contract before harmonization

    @field_validator('year', mode='before')
    @classmethod
    def convert_year_to_string(cls, v):
        """Convert year to string, handling int or string input."""
        if v is None:
            return None
        return str(v)

    @field_validator('season_level', mode='before')
    @classmethod
    def validate_season_level(cls, v):
        """Validate and default season level."""
        if v is None:
            return "high"
        if v not in ('low', 'high', 'peak'):
            return "high"
        return v


class ExtractedRateResponse(BaseModel):
    """Extracted rate."""
    room_code: str
    season_code: Optional[str] = None
    bed_type: str = "DBL"
    meal_plan: str = "BB"
    cost: float
    currency: str = "EUR"
    single_supplement: Optional[float] = None
    extra_adult: Optional[float] = None
    extra_child: Optional[float] = None


class ExtractedContractInfoResponse(BaseModel):
    """Extracted contract metadata."""
    name: Optional[str] = None
    reference: Optional[str] = None
    valid_from: Optional[str] = None  # YYYY-MM-DD
    valid_to: Optional[str] = None    # YYYY-MM-DD
    currency: Optional[str] = None


class ExtractionResultResponse(BaseModel):
    """Complete extraction result."""
    contract_info: Optional[ExtractedContractInfoResponse] = None
    room_categories: List[ExtractedRoomCategoryResponse]
    seasons: List[ExtractedSeasonResponse]
    rates: List[ExtractedRateResponse]
    source_file: Optional[str] = None
    extracted_at: Optional[str] = None
    confidence_score: Optional[float] = None
    warnings: Optional[List[str]] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/extract-rates", response_model=ExtractionResultResponse)
async def extract_rates_from_contract(
    file: UploadFile = File(...),
    supplier_id: int = Form(...),
    accommodation_id: Optional[int] = Form(None),
    db: DbSession = None,
    user: CurrentUser = None,
    tenant: CurrentTenant = None,
):
    """
    Extract room categories, seasons, and rates from a PDF contract using AI.

    This endpoint accepts a PDF file and uses Claude Vision to analyze and extract:
    - Room categories (names, codes, capacities, bed types)
    - Seasons (names, dates, yearly/recurring)
    - Rates (per room/season/meal plan combination)

    The extracted data is returned for user review before final import.
    """
    # Validate file type
    if not file.content_type or 'pdf' not in file.content_type.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted"
        )

    # Check file size (max 10 MB)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size must not exceed 10 MB"
        )

    # Get extraction service
    try:
        service = get_extraction_service()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI extraction service not configured"
        )

    # Extract rates
    try:
        result = await service.extract_rates_from_pdf(
            pdf_content=content,
            filename=file.filename,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract data from PDF: {str(e)}"
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI service error: {str(e)}"
        )

    # Return result
    return ExtractionResultResponse(
        contract_info=ExtractedContractInfoResponse(**result.contract_info.to_dict()) if result.contract_info else None,
        room_categories=[
            ExtractedRoomCategoryResponse(**cat.to_dict())
            for cat in result.room_categories
        ],
        seasons=[
            ExtractedSeasonResponse(**season.to_dict())
            for season in result.seasons
        ],
        rates=[
            ExtractedRateResponse(**rate.to_dict())
            for rate in result.rates
        ],
        source_file=result.source_file,
        extracted_at=result.extracted_at,
        confidence_score=result.confidence_score,
        warnings=result.warnings,
    )


class ImportExtractedRatesRequest(BaseModel):
    """Request body for importing extracted rates."""
    supplier_id: int
    accommodation_id: Optional[int] = None
    accommodation_name: Optional[str] = None
    contract_info: Optional[ExtractedContractInfoResponse] = None  # Contract metadata
    categories: List[ExtractedRoomCategoryResponse]
    seasons: List[ExtractedSeasonResponse]
    rates: List[ExtractedRateResponse]
    warnings: Optional[List[str]] = None  # AI-extracted warnings to store with contract


class ImportResultResponse(BaseModel):
    """Response for import operation."""
    success: bool
    accommodation_id: int
    accommodation_created: bool
    contract_id: Optional[int] = None  # Created contract ID
    contract_created: bool = False
    created: dict
    reused: dict  # Entities that already existed and were reused


@router.post("/import-extracted-rates", response_model=ImportResultResponse)
async def import_extracted_rates(
    request: ImportExtractedRatesRequest,
    db: DbSession = None,
    user: CurrentUser = None,
    tenant: CurrentTenant = None,
):
    """
    Import previously extracted rates into the database.

    This endpoint creates the room categories, seasons, and rates
    that were extracted and validated by the user.

    If no accommodation_id is provided, it will create a new accommodation
    using the supplier name or the provided accommodation_name.
    """
    import logging
    from datetime import date, datetime
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.models.accommodation import (
        Accommodation,
        RoomCategory,
        AccommodationSeason,
        RoomRate,
    )
    from app.models.supplier import Supplier
    from app.models.contract import Contract

    logger = logging.getLogger(__name__)

    accommodation_created = False
    contract_created = False
    contract_id = None
    accommodation_id = request.accommodation_id

    # If no accommodation_id, create one
    if not accommodation_id:
        # Get supplier to use its name
        supplier_result = await db.execute(
            select(Supplier).where(
                Supplier.id == request.supplier_id,
                Supplier.tenant_id == tenant.id,
            )
        )
        supplier = supplier_result.scalar_one_or_none()

        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplier not found"
            )

        # Use provided name or supplier name
        acc_name = request.accommodation_name or supplier.name

        # Create new accommodation
        accommodation = Accommodation(
            tenant_id=tenant.id,
            supplier_id=request.supplier_id,
            name=acc_name,
            external_provider="manual",
            is_active=True,
        )
        db.add(accommodation)
        await db.flush()
        accommodation_id = accommodation.id
        accommodation_created = True
    else:
        # Verify accommodation exists and belongs to tenant
        result = await db.execute(
            select(Accommodation).where(
                Accommodation.id == accommodation_id,
                Accommodation.tenant_id == tenant.id,
            )
        )
        accommodation = result.scalar_one_or_none()

        if not accommodation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Accommodation not found"
            )

    # Maps for linking rates to created entities
    category_map = {}  # code -> id
    season_map = {}    # code -> id

    # Counters for created vs reused
    created_categories = 0
    reused_categories = 0
    created_seasons = 0
    reused_seasons = 0

    # Load existing room categories for this accommodation
    existing_categories_result = await db.execute(
        select(RoomCategory).where(RoomCategory.accommodation_id == accommodation_id)
    )
    existing_categories = existing_categories_result.scalars().all()
    existing_category_by_code = {cat.code: cat for cat in existing_categories if cat.code}
    existing_category_by_name = {cat.name: cat for cat in existing_categories}

    # Load existing seasons for this accommodation
    existing_seasons_result = await db.execute(
        select(AccommodationSeason).where(AccommodationSeason.accommodation_id == accommodation_id)
    )
    existing_seasons = existing_seasons_result.scalars().all()
    # Index by code+year and name+year to distinguish seasons across years
    existing_season_by_code_year = {f"{s.code}|{s.year}": s for s in existing_seasons if s.code}
    existing_season_by_name_year = {f"{s.name}|{s.year}": s for s in existing_seasons}

    # Create room categories (or reuse existing)
    for cat_data in request.categories:
        lookup_key = cat_data.code or cat_data.name

        # Check if category already exists (by code first, then by name)
        existing = None
        if cat_data.code and cat_data.code in existing_category_by_code:
            existing = existing_category_by_code[cat_data.code]
        elif cat_data.name in existing_category_by_name:
            existing = existing_category_by_name[cat_data.name]

        if existing:
            # Reuse existing category
            category_map[lookup_key] = existing.id
            reused_categories += 1
        else:
            # Create new category
            category = RoomCategory(
                accommodation_id=accommodation_id,
                name=cat_data.name,
                code=cat_data.code,
                description=cat_data.description,
                max_occupancy=cat_data.max_occupancy or 2,
                max_adults=cat_data.max_adults or 2,
                max_children=cat_data.max_children or 0,
                min_occupancy=1,
                available_bed_types=cat_data.available_bed_types or ["DBL"],
                is_active=True,
                sort_order=0,
            )
            db.add(category)
            await db.flush()
            category_map[lookup_key] = category.id
            created_categories += 1
            # Add to existing maps for subsequent lookups
            if cat_data.code:
                existing_category_by_code[cat_data.code] = category
            existing_category_by_name[cat_data.name] = category

    # Create seasons (or reuse existing)
    for season_data in request.seasons:
        lookup_key = season_data.code or season_data.name
        year = season_data.year

        # Check if season already exists (by code+year first, then by name+year)
        # This allows having "Haute Saison 2025-2026" AND "Haute Saison 2026-2027"
        existing = None
        code_year_key = f"{season_data.code}|{year}" if season_data.code else None
        name_year_key = f"{season_data.name}|{year}"

        if code_year_key and code_year_key in existing_season_by_code_year:
            existing = existing_season_by_code_year[code_year_key]
        elif name_year_key in existing_season_by_name_year:
            existing = existing_season_by_name_year[name_year_key]

        if existing:
            # Reuse existing season (same code/name AND same year)
            season_map[lookup_key] = existing.id
            reused_seasons += 1
            logger.info(f"Reusing existing season: {existing.name} ({existing.year})")
        else:
            # Create new season
            # Convert MM-DD dates to YYYY-MM-DD format if year is provided
            start_date = _build_full_date(season_data.start_date, year, is_end_date=False)
            end_date = _build_full_date(season_data.end_date, year, is_end_date=True)

            season = AccommodationSeason(
                accommodation_id=accommodation_id,
                name=season_data.name,
                code=season_data.code,
                original_name=season_data.original_name,  # Store original name from contract
                season_type="recurring" if not year else "fixed",
                start_date=start_date,
                end_date=end_date,
                year=year,
                season_level=season_data.season_level or "high",
                priority=1,
                is_active=True,
            )
            db.add(season)
            await db.flush()
            season_map[lookup_key] = season.id
            created_seasons += 1
            logger.info(f"Created new season: {season.name} ({season.year}) with dates {start_date} - {end_date}")
            # Add to existing maps for subsequent lookups
            if season_data.code:
                existing_season_by_code_year[f"{season_data.code}|{year}"] = season
            existing_season_by_name_year[f"{season_data.name}|{year}"] = season

    # Create rates
    created_rates = 0
    skipped_rates = 0
    for rate_data in request.rates:
        room_category_id = category_map.get(rate_data.room_code)
        if not room_category_id:
            logger.warning(f"Room code '{rate_data.room_code}' not found in category_map, skipping rate")
            skipped_rates += 1
            continue

        season_id = None
        if rate_data.season_code:
            season_id = season_map.get(rate_data.season_code)
            if not season_id:
                logger.warning(f"Season code '{rate_data.season_code}' not found in season_map, setting season_id to None")

        rate = RoomRate(
            accommodation_id=accommodation_id,
            room_category_id=room_category_id,
            season_id=season_id,
            bed_type=rate_data.bed_type,
            meal_plan=rate_data.meal_plan,
            base_occupancy=2,
            rate_type="per_night",
            cost=rate_data.cost,
            currency=rate_data.currency,
            single_supplement=rate_data.single_supplement,
            extra_adult=rate_data.extra_adult,
            extra_child=rate_data.extra_child,
            is_active=True,
        )
        db.add(rate)
        created_rates += 1

    if skipped_rates > 0:
        logger.warning(f"Skipped {skipped_rates} rates due to missing room categories")

    # Create contract if contract_info is provided
    if request.contract_info:
        # Parse dates
        valid_from = None
        valid_to = None

        if request.contract_info.valid_from:
            try:
                valid_from = datetime.strptime(request.contract_info.valid_from, "%Y-%m-%d").date()
            except ValueError:
                valid_from = date.today()

        if request.contract_info.valid_to:
            try:
                valid_to = datetime.strptime(request.contract_info.valid_to, "%Y-%m-%d").date()
            except ValueError:
                # Default to 1 year from now
                valid_to = date(date.today().year + 1, date.today().month, date.today().day)

        # Default dates if not provided
        if not valid_from:
            valid_from = date.today()
        if not valid_to:
            valid_to = date(date.today().year + 1, date.today().month, date.today().day)

        # Create contract name
        contract_name = request.contract_info.name
        if not contract_name:
            # Generate from accommodation name and dates
            contract_name = f"Contrat Tarifs {valid_from.year}"
            if valid_to.year != valid_from.year:
                contract_name = f"Contrat Tarifs {valid_from.year}-{valid_to.year}"

        contract = Contract(
            tenant_id=tenant.id,
            supplier_id=request.supplier_id,
            name=contract_name,
            reference=request.contract_info.reference,
            valid_from=valid_from,
            valid_to=valid_to,
            status="active",
            ai_extracted_at=datetime.utcnow(),
            ai_warnings=request.warnings,  # Store AI-extracted warnings
        )
        db.add(contract)
        await db.flush()
        contract_id = contract.id
        contract_created = True

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError during import: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database conflict during import: {str(e.orig) if e.orig else str(e)}"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error during import: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during import: {str(e)}"
        )

    return ImportResultResponse(
        success=True,
        accommodation_id=accommodation_id,
        accommodation_created=accommodation_created,
        contract_id=contract_id,
        contract_created=contract_created,
        created={
            "categories": created_categories,
            "seasons": created_seasons,
            "rates": created_rates,
        },
        reused={
            "categories": reused_categories,
            "seasons": reused_seasons,
        }
    )
