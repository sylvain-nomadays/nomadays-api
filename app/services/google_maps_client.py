"""
Google Maps API Client for geocoding and routing.

This service provides:
- Places Autocomplete: Search locations by name (e.g., "Chiang Mai")
- Geocoding: Convert place names/IDs to coordinates
- Directions: Calculate routes between locations with distance/duration
- Distance Matrix: Get distances between multiple locations

Usage:
    client = GoogleMapsClient(api_key="your-api-key")

    # Search for a place
    results = await client.places_autocomplete("Chiang Mai", country="TH")

    # Get coordinates for a place
    location = await client.geocode("Chiang Mai, Thailand")

    # Get directions between two points
    route = await client.get_directions(
        origin=(13.7563, 100.5018),  # Bangkok
        destination=(18.7883, 98.9853),  # Chiang Mai
    )
"""

import os
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal
import httpx
from dataclasses import dataclass


@dataclass
class GeocodingResult:
    """Result from geocoding a location."""
    place_id: str
    name: str
    formatted_address: str
    lat: Decimal
    lng: Decimal
    country_code: Optional[str] = None
    region: Optional[str] = None
    types: List[str] = None

    def __post_init__(self):
        if self.types is None:
            self.types = []


@dataclass
class PlaceAutocompleteResult:
    """Result from places autocomplete search."""
    place_id: str
    description: str
    main_text: str
    secondary_text: str
    types: List[str] = None

    def __post_init__(self):
        if self.types is None:
            self.types = []


@dataclass
class DirectionsResult:
    """Result from directions API."""
    distance_km: Decimal
    duration_minutes: int
    polyline: str
    start_address: str
    end_address: str


class GoogleMapsError(Exception):
    """Base exception for Google Maps API errors."""
    pass


class GoogleMapsClient:
    """
    Async client for Google Maps APIs.

    Supports:
    - Places Autocomplete (for searching locations by name)
    - Geocoding (for getting coordinates)
    - Directions (for routes between locations)
    """

    BASE_URL = "https://maps.googleapis.com/maps/api"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Google Maps client.

        Args:
            api_key: Google Maps API key. If not provided, reads from GOOGLE_MAPS_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        if not self.api_key:
            raise GoogleMapsError("Google Maps API key not configured")

    async def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make an async request to Google Maps API."""
        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}/json"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                error_msg = data.get("error_message", data.get("status", "Unknown error"))
                raise GoogleMapsError(f"Google Maps API error: {error_msg}")

            return data

    async def places_autocomplete(
        self,
        query: str,
        country: Optional[str] = None,
        types: Optional[str] = "(regions)",
        language: str = "fr",
    ) -> List[PlaceAutocompleteResult]:
        """
        Search for places using autocomplete.

        This is the main method for the "type Chiang Mai and get results" use case.

        Args:
            query: Search query (e.g., "Chiang Mai")
            country: ISO 2-letter country code to restrict results (e.g., "TH")
            types: Place types to include. Use "(regions)" for cities, "(cities)" for cities only.
            language: Language for results (default: French)

        Returns:
            List of autocomplete suggestions.
        """
        params = {
            "input": query,
            "language": language,
        }
        if country:
            params["components"] = f"country:{country}"
        if types:
            params["types"] = types

        data = await self._request("place/autocomplete", params)

        results = []
        for prediction in data.get("predictions", []):
            results.append(PlaceAutocompleteResult(
                place_id=prediction["place_id"],
                description=prediction["description"],
                main_text=prediction.get("structured_formatting", {}).get("main_text", ""),
                secondary_text=prediction.get("structured_formatting", {}).get("secondary_text", ""),
                types=prediction.get("types", []),
            ))
        return results

    async def geocode(
        self,
        address: Optional[str] = None,
        place_id: Optional[str] = None,
        language: str = "fr",
    ) -> Optional[GeocodingResult]:
        """
        Get coordinates for an address or place ID.

        Args:
            address: Address to geocode (e.g., "Chiang Mai, Thailand")
            place_id: Google Place ID (preferred, more accurate)
            language: Language for results

        Returns:
            GeocodingResult with coordinates, or None if not found.
        """
        if not address and not place_id:
            raise ValueError("Either address or place_id must be provided")

        params = {"language": language}
        if place_id:
            params["place_id"] = place_id
        else:
            params["address"] = address

        data = await self._request("geocode", params)

        results = data.get("results", [])
        if not results:
            return None

        result = results[0]
        location = result["geometry"]["location"]

        # Extract country code and region from address components
        country_code = None
        region = None
        for component in result.get("address_components", []):
            if "country" in component.get("types", []):
                country_code = component.get("short_name")
            elif "administrative_area_level_1" in component.get("types", []):
                region = component.get("long_name")

        return GeocodingResult(
            place_id=result["place_id"],
            name=result.get("address_components", [{}])[0].get("long_name", ""),
            formatted_address=result["formatted_address"],
            lat=Decimal(str(location["lat"])),
            lng=Decimal(str(location["lng"])),
            country_code=country_code,
            region=region,
            types=result.get("types", []),
        )

    async def get_place_details(
        self,
        place_id: str,
        language: str = "fr",
    ) -> Optional[GeocodingResult]:
        """
        Get detailed information about a place by its ID.

        Args:
            place_id: Google Place ID
            language: Language for results

        Returns:
            GeocodingResult with full details.
        """
        params = {
            "place_id": place_id,
            "fields": "place_id,name,formatted_address,geometry,address_components,types",
            "language": language,
        }

        data = await self._request("place/details", params)
        result = data.get("result")
        if not result:
            return None

        location = result.get("geometry", {}).get("location", {})

        # Extract country code and region
        country_code = None
        region = None
        for component in result.get("address_components", []):
            if "country" in component.get("types", []):
                country_code = component.get("short_name")
            elif "administrative_area_level_1" in component.get("types", []):
                region = component.get("long_name")

        return GeocodingResult(
            place_id=result["place_id"],
            name=result.get("name", ""),
            formatted_address=result.get("formatted_address", ""),
            lat=Decimal(str(location.get("lat", 0))),
            lng=Decimal(str(location.get("lng", 0))),
            country_code=country_code,
            region=region,
            types=result.get("types", []),
        )

    async def get_directions(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        mode: str = "driving",
        language: str = "fr",
    ) -> Optional[DirectionsResult]:
        """
        Get directions between two points.

        Args:
            origin: (lat, lng) tuple for start point
            destination: (lat, lng) tuple for end point
            mode: Travel mode (driving, walking, transit)
            language: Language for results

        Returns:
            DirectionsResult with distance, duration, and polyline.
        """
        params = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "mode": mode,
            "language": language,
        }

        data = await self._request("directions", params)

        routes = data.get("routes", [])
        if not routes:
            return None

        route = routes[0]
        leg = route["legs"][0]

        return DirectionsResult(
            distance_km=Decimal(str(leg["distance"]["value"] / 1000)),
            duration_minutes=leg["duration"]["value"] // 60,
            polyline=route["overview_polyline"]["points"],
            start_address=leg["start_address"],
            end_address=leg["end_address"],
        )

    async def get_distance_matrix(
        self,
        origins: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
        mode: str = "driving",
    ) -> Dict[str, Any]:
        """
        Get distances and durations between multiple origins and destinations.

        Args:
            origins: List of (lat, lng) tuples
            destinations: List of (lat, lng) tuples
            mode: Travel mode

        Returns:
            Matrix of distances and durations.
        """
        params = {
            "origins": "|".join(f"{lat},{lng}" for lat, lng in origins),
            "destinations": "|".join(f"{lat},{lng}" for lat, lng in destinations),
            "mode": mode,
        }

        data = await self._request("distancematrix", params)

        # Parse the matrix into a more usable format
        results = []
        for i, row in enumerate(data.get("rows", [])):
            row_results = []
            for j, element in enumerate(row.get("elements", [])):
                if element.get("status") == "OK":
                    row_results.append({
                        "distance_km": element["distance"]["value"] / 1000,
                        "duration_minutes": element["duration"]["value"] // 60,
                    })
                else:
                    row_results.append(None)
            results.append(row_results)

        return {
            "origin_addresses": data.get("origin_addresses", []),
            "destination_addresses": data.get("destination_addresses", []),
            "matrix": results,
        }


# Singleton instance for easy access
_client: Optional[GoogleMapsClient] = None


def get_google_maps_client() -> GoogleMapsClient:
    """Get the singleton Google Maps client instance."""
    global _client
    if _client is None:
        _client = GoogleMapsClient()
    return _client


# Helper functions for simpler usage
async def search_places(query: str, country: Optional[str] = None) -> List[PlaceAutocompleteResult]:
    """Quick helper to search for places."""
    client = get_google_maps_client()
    return await client.places_autocomplete(query, country=country)


async def geocode_place(place_id: str) -> Optional[GeocodingResult]:
    """Quick helper to geocode a place by ID."""
    client = get_google_maps_client()
    return await client.get_place_details(place_id)


async def geocode_address(address: str) -> Optional[GeocodingResult]:
    """Quick helper to geocode an address."""
    client = get_google_maps_client()
    return await client.geocode(address=address)
