"""
Trip Locations API - Geographic waypoints and routing.

Provides:
- CRUD for trip locations
- Places autocomplete (search by name)
- Geocoding (name → coordinates)
- Route calculation between locations
"""

from typing import List, Optional
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_current_user, get_tenant_id
from app.models.trip_location import TripLocation, TripRoute
from app.models.trip import Trip
from app.services.google_maps_client import (
    GoogleMapsClient,
    get_google_maps_client,
    GoogleMapsError,
)

router = APIRouter(prefix="/trips/{trip_id}/locations", tags=["Trip Locations"])


# ============================================================================
# Schemas
# ============================================================================

class PlaceAutocompleteRequest(BaseModel):
    """Request for places autocomplete."""
    query: str = Field(..., min_length=2, description="Search query")
    country: Optional[str] = Field(None, max_length=2, description="ISO country code")


class PlaceAutocompleteResult(BaseModel):
    """Result from places autocomplete."""
    place_id: str
    description: str
    main_text: str
    secondary_text: str


class GeocodeRequest(BaseModel):
    """Request to geocode a place."""
    place_id: Optional[str] = None
    address: Optional[str] = None


class GeocodeResult(BaseModel):
    """Result from geocoding."""
    place_id: str
    name: str
    formatted_address: str
    lat: float
    lng: float
    country_code: Optional[str] = None
    region: Optional[str] = None


class TripLocationCreate(BaseModel):
    """Schema for creating a trip location."""
    name: str = Field(..., min_length=1, max_length=255)
    place_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    day_number: Optional[int] = None
    location_type: str = "overnight"
    description: Optional[str] = None
    sort_order: int = 0


class TripLocationUpdate(BaseModel):
    """Schema for updating a trip location."""
    name: Optional[str] = None
    place_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    day_number: Optional[int] = None
    location_type: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class TripLocationResponse(BaseModel):
    """Response schema for a trip location."""
    id: int
    trip_id: int
    name: str
    place_id: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    address: Optional[str]
    country_code: Optional[str]
    region: Optional[str]
    day_number: Optional[int]
    location_type: str
    description: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


class TripRouteResponse(BaseModel):
    """Response schema for a route between locations."""
    id: int
    from_location_id: int
    to_location_id: int
    distance_km: Optional[float]
    duration_minutes: Optional[int]
    duration_formatted: str
    polyline: Optional[str]
    travel_mode: str

    class Config:
        from_attributes = True


class TripMapDataResponse(BaseModel):
    """Complete map data for a trip (locations + routes)."""
    locations: List[TripLocationResponse]
    routes: List[TripRouteResponse]


# ============================================================================
# Helper functions
# ============================================================================

async def get_trip_or_404(
    trip_id: int,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> Trip:
    """Get trip by ID or raise 404."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant_id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


async def get_location_or_404(
    location_id: int,
    trip_id: int,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> TripLocation:
    """Get location by ID or raise 404."""
    result = await db.execute(
        select(TripLocation)
        .where(
            TripLocation.id == location_id,
            TripLocation.trip_id == trip_id,
            TripLocation.tenant_id == tenant_id,
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


# ============================================================================
# Places Autocomplete Endpoints (no trip_id required)
# ============================================================================

places_router = APIRouter(prefix="/places", tags=["Places"])


@places_router.post("/autocomplete", response_model=List[PlaceAutocompleteResult])
async def places_autocomplete(
    request: PlaceAutocompleteRequest,
    current_user=Depends(get_current_user),
):
    """
    Search for places using autocomplete.

    Use this to let users type "Chiang Mai" and get suggestions.
    """
    try:
        client = get_google_maps_client()
        results = await client.places_autocomplete(
            query=request.query,
            country=request.country,
        )
        return [
            PlaceAutocompleteResult(
                place_id=r.place_id,
                description=r.description,
                main_text=r.main_text,
                secondary_text=r.secondary_text,
            )
            for r in results
        ]
    except GoogleMapsError as e:
        raise HTTPException(status_code=500, detail=str(e))


@places_router.post("/geocode", response_model=Optional[GeocodeResult])
async def geocode_place(
    request: GeocodeRequest,
    current_user=Depends(get_current_user),
):
    """
    Geocode a place ID or address to get coordinates.

    Preferred: Use place_id from autocomplete results for accuracy.
    """
    if not request.place_id and not request.address:
        raise HTTPException(
            status_code=400,
            detail="Either place_id or address must be provided"
        )

    try:
        client = get_google_maps_client()
        if request.place_id:
            result = await client.get_place_details(request.place_id)
        else:
            result = await client.geocode(address=request.address)

        if not result:
            return None

        return GeocodeResult(
            place_id=result.place_id,
            name=result.name,
            formatted_address=result.formatted_address,
            lat=float(result.lat),
            lng=float(result.lng),
            country_code=result.country_code,
            region=result.region,
        )
    except GoogleMapsError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Trip Location CRUD Endpoints
# ============================================================================

@router.get("", response_model=List[TripLocationResponse])
async def list_trip_locations(
    trip_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """List all locations for a trip."""
    # Verify trip exists
    await get_trip_or_404(trip_id, tenant_id, db)

    result = await db.execute(
        select(TripLocation)
        .where(TripLocation.trip_id == trip_id, TripLocation.tenant_id == tenant_id)
        .order_by(TripLocation.sort_order, TripLocation.day_number)
    )
    return result.scalars().all()


@router.post("", response_model=TripLocationResponse, status_code=201)
async def create_trip_location(
    trip_id: int,
    location_data: TripLocationCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """
    Create a new location for a trip.

    If only name is provided, you can call /places/geocode first to get coordinates.
    """
    # Verify trip exists
    await get_trip_or_404(trip_id, tenant_id, db)

    location = TripLocation(
        trip_id=trip_id,
        tenant_id=tenant_id,
        **location_data.model_dump(),
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


@router.post("/geocode-and-create", response_model=TripLocationResponse, status_code=201)
async def geocode_and_create_location(
    trip_id: int,
    name: str = Query(..., description="Location name to geocode"),
    place_id: Optional[str] = Query(None, description="Google Place ID (preferred)"),
    day_number: Optional[int] = Query(None),
    location_type: str = Query("overnight"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """
    Geocode a location name and create it in one call.

    This is the main endpoint for the "type Chiang Mai and add to map" use case.
    """
    # Verify trip exists
    await get_trip_or_404(trip_id, tenant_id, db)

    try:
        client = get_google_maps_client()

        # Geocode the location
        if place_id:
            geo_result = await client.get_place_details(place_id)
        else:
            geo_result = await client.geocode(address=name)

        if not geo_result:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find location: {name}"
            )

        # Get max sort_order for this trip
        result = await db.execute(
            select(TripLocation.sort_order)
            .where(TripLocation.trip_id == trip_id)
            .order_by(TripLocation.sort_order.desc())
            .limit(1)
        )
        max_order = result.scalar() or 0

        # Create the location
        location = TripLocation(
            trip_id=trip_id,
            tenant_id=tenant_id,
            name=geo_result.name or name,
            place_id=geo_result.place_id,
            lat=geo_result.lat,
            lng=geo_result.lng,
            address=geo_result.formatted_address,
            country_code=geo_result.country_code,
            region=geo_result.region,
            day_number=day_number,
            location_type=location_type,
            sort_order=max_order + 1,
        )
        db.add(location)
        await db.commit()
        await db.refresh(location)
        return location

    except GoogleMapsError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{location_id}", response_model=TripLocationResponse)
async def get_trip_location(
    trip_id: int,
    location_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Get a specific location."""
    return await get_location_or_404(location_id, trip_id, tenant_id, db)


@router.patch("/{location_id}", response_model=TripLocationResponse)
async def update_trip_location(
    trip_id: int,
    location_id: int,
    location_data: TripLocationUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Update a location."""
    location = await get_location_or_404(location_id, trip_id, tenant_id, db)

    for field, value in location_data.model_dump(exclude_unset=True).items():
        setattr(location, field, value)

    await db.commit()
    await db.refresh(location)
    return location


@router.delete("/{location_id}", status_code=204)
async def delete_trip_location(
    trip_id: int,
    location_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """Delete a location."""
    location = await get_location_or_404(location_id, trip_id, tenant_id, db)
    await db.delete(location)
    await db.commit()


# ============================================================================
# Route Calculation Endpoints
# ============================================================================

@router.post("/calculate-routes", response_model=List[TripRouteResponse])
async def calculate_routes(
    trip_id: int,
    travel_mode: str = Query("driving", description="Travel mode: driving, walking, transit"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """
    Calculate routes between all consecutive locations.

    This will calculate distance and duration between each pair of locations
    in order (by sort_order/day_number).
    """
    # Get all locations with coordinates, ordered
    result = await db.execute(
        select(TripLocation)
        .where(
            TripLocation.trip_id == trip_id,
            TripLocation.tenant_id == tenant_id,
            TripLocation.lat.isnot(None),
            TripLocation.lng.isnot(None),
        )
        .order_by(TripLocation.sort_order, TripLocation.day_number)
    )
    locations = list(result.scalars().all())

    if len(locations) < 2:
        return []

    # Delete existing routes for this trip
    await db.execute(
        delete(TripRoute).where(TripRoute.trip_id == trip_id)
    )

    try:
        client = get_google_maps_client()
        routes = []

        # Calculate route for each consecutive pair
        for i in range(len(locations) - 1):
            from_loc = locations[i]
            to_loc = locations[i + 1]

            directions = await client.get_directions(
                origin=(float(from_loc.lat), float(from_loc.lng)),
                destination=(float(to_loc.lat), float(to_loc.lng)),
                mode=travel_mode,
            )

            if directions:
                route = TripRoute(
                    trip_id=trip_id,
                    tenant_id=tenant_id,
                    from_location_id=from_loc.id,
                    to_location_id=to_loc.id,
                    distance_km=directions.distance_km,
                    duration_minutes=directions.duration_minutes,
                    polyline=directions.polyline,
                    travel_mode=travel_mode,
                )
                db.add(route)
                routes.append(route)

        await db.commit()

        # Refresh to get IDs
        for route in routes:
            await db.refresh(route)

        return routes

    except GoogleMapsError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/map-data", response_model=TripMapDataResponse)
async def get_map_data(
    trip_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    current_user=Depends(get_current_user),
):
    """
    Get all map data for a trip (locations + routes).

    Use this endpoint to render the complete map.
    """
    # Get locations
    locations_result = await db.execute(
        select(TripLocation)
        .where(TripLocation.trip_id == trip_id, TripLocation.tenant_id == tenant_id)
        .order_by(TripLocation.sort_order, TripLocation.day_number)
    )
    locations = locations_result.scalars().all()

    # Get routes
    routes_result = await db.execute(
        select(TripRoute)
        .where(TripRoute.trip_id == trip_id, TripRoute.tenant_id == tenant_id)
    )
    routes = routes_result.scalars().all()

    return TripMapDataResponse(
        locations=[TripLocationResponse.model_validate(loc) for loc in locations],
        routes=[
            TripRouteResponse(
                id=r.id,
                from_location_id=r.from_location_id,
                to_location_id=r.to_location_id,
                distance_km=float(r.distance_km) if r.distance_km else None,
                duration_minutes=r.duration_minutes,
                duration_formatted=r.duration_formatted,
                polyline=r.polyline,
                travel_mode=r.travel_mode,
            )
            for r in routes
        ],
    )
