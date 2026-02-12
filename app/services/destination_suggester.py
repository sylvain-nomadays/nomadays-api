"""
AI-powered destination suggestion service.

Uses Claude AI to generate a list of top tourist destinations for a given country,
then geocodes each one via Google Maps API.

Flow:
1. Claude AI generates ~20 destinations (name, type, descriptions FR/EN)
2. Google Maps geocodes each (lat/lng, place_id) in parallel with semaphore
3. Returns enriched list for admin review
"""

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List

from anthropic import Anthropic

from app.config import get_settings
from app.services.google_maps_client import get_google_maps_client, GoogleMapsClient

logger = logging.getLogger(__name__)

settings = get_settings()


# ============================================================================
# Country Names (for Claude prompt)
# ============================================================================

COUNTRY_NAMES = {
    "TH": "Thaïlande",
    "VN": "Vietnam",
    "KH": "Cambodge",
    "LA": "Laos",
    "MM": "Myanmar",
    "ID": "Indonésie",
    "MY": "Malaisie",
    "PH": "Philippines",
    "JP": "Japon",
    "CN": "Chine",
    "IN": "Inde",
    "NP": "Népal",
    "LK": "Sri Lanka",
    "MA": "Maroc",
    "EG": "Égypte",
    "ZA": "Afrique du Sud",
    "KE": "Kenya",
    "TZ": "Tanzanie",
    "MX": "Mexique",
    "PE": "Pérou",
    "BR": "Brésil",
    "AR": "Argentine",
    "CL": "Chili",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "TR": "Turquie",
    "GR": "Grèce",
    "IT": "Italie",
    "ES": "Espagne",
    "PT": "Portugal",
    "FR": "France",
    "HR": "Croatie",
    "IS": "Islande",
    "NO": "Norvège",
}


def get_country_name(country_code: str) -> str:
    """Get country name from code, fallback to code itself."""
    return COUNTRY_NAMES.get(country_code.upper(), country_code)


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class SuggestedDestination:
    """A destination suggestion from Claude AI, enriched with geocoding."""
    name: str
    location_type: str  # city, region, area
    description_fr: str
    description_en: str
    sort_order: int
    country_code: str
    # Geocoding results (filled by Google Maps, None if geocoding failed)
    lat: Optional[Decimal] = None
    lng: Optional[Decimal] = None
    google_place_id: Optional[str] = None
    formatted_address: Optional[str] = None
    geocoding_success: bool = False


# ============================================================================
# Slugification
# ============================================================================

def make_slug(name: str) -> str:
    """
    Generate a URL-friendly slug from a destination name.

    Examples:
        "Baie d'Halong" → "baie-dhalong"
        "Chiang Mai" → "chiang-mai"
        "Hô Chi Minh Ville" → "ho-chi-minh-ville"
        "São Paulo" → "sao-paulo"
    """
    # Normalize unicode (accents → ascii)
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = slug.lower()
    # Replace non-alphanumeric chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug


# ============================================================================
# Claude AI Prompt
# ============================================================================

SUGGEST_PROMPT = """Tu es un expert en tourisme réceptif (DMC - Destination Management Company).
Pour le pays "{country_name}" (code: {country_code}), génère exactement {count} destinations touristiques incontournables qu'un DMC proposerait à ses clients.

Mélange intelligemment :
- Des villes principales (type "city")
- Des régions touristiques (type "region")
- Des zones naturelles ou sites emblématiques (type "area")

Trie par importance touristique (1 = la plus importante/visitée).

Pour chaque destination, fournis :
- name : le nom courant international (ex: "Chiang Mai", "Baie d'Halong", "Bali")
- location_type : "city", "region" ou "area"
- description_fr : 1-2 phrases en français décrivant la destination
- description_en : 1-2 phrases en anglais décrivant la destination
- sort_order : rang d'importance (1 = plus important)

IMPORTANT : Retourne UNIQUEMENT du JSON valide, sans markdown, sans backticks, sans commentaires :
{{"destinations": [{{"name": "...", "location_type": "city", "description_fr": "...", "description_en": "...", "sort_order": 1}}]}}"""


# ============================================================================
# Service
# ============================================================================

class DestinationSuggester:
    """
    Service to suggest tourist destinations using Claude AI
    and enrich them with Google Maps geocoding.
    """

    def __init__(self):
        self.claude = Anthropic(api_key=settings.anthropic_api_key)
        # Google Maps is optional — geocoding is skipped if not configured
        try:
            self.maps: Optional[GoogleMapsClient] = get_google_maps_client()
        except Exception as e:
            logger.warning(f"Google Maps not configured, geocoding disabled: {e}")
            self.maps = None

    async def suggest(
        self,
        country_code: str,
        country_name: Optional[str] = None,
        count: int = 20,
    ) -> List[SuggestedDestination]:
        """
        Generate destination suggestions for a country.

        1. Calls Claude AI to get a structured list of destinations
        2. Geocodes each destination via Google Maps (parallel with semaphore)
        3. Returns the enriched list

        Args:
            country_code: ISO 2-letter country code (e.g., "TH")
            country_name: Country name override (auto-detected if None)
            count: Number of destinations to suggest (10-30)

        Returns:
            List of SuggestedDestination with geocoding data
        """
        country_code = country_code.upper()
        if not country_name:
            country_name = get_country_name(country_code)

        count = max(10, min(count, 30))

        # Step 1: Claude AI generates destination list
        logger.info(f"Requesting {count} destination suggestions for {country_name} ({country_code})")
        destinations = await self._ask_claude(country_code, country_name, count)
        logger.info(f"Claude returned {len(destinations)} destinations for {country_name}")

        # Step 2: Geocode each destination in parallel (max 5 concurrent)
        if self.maps:
            semaphore = asyncio.Semaphore(5)

            async def geocode_one(dest: SuggestedDestination) -> SuggestedDestination:
                async with semaphore:
                    return await self._geocode_destination(dest, country_code)

            enriched = await asyncio.gather(
                *[geocode_one(d) for d in destinations],
                return_exceptions=True,
            )

            # Filter out exceptions, keep valid results
            results: List[SuggestedDestination] = []
            for item in enriched:
                if isinstance(item, SuggestedDestination):
                    results.append(item)
                elif isinstance(item, Exception):
                    logger.warning(f"Geocoding failed for a destination: {item}")
        else:
            logger.info("Skipping geocoding (Google Maps not configured)")
            results = destinations

        # Sort by sort_order
        results.sort(key=lambda d: d.sort_order)

        logger.info(
            f"Suggestion complete for {country_name}: "
            f"{len(results)} destinations, "
            f"{sum(1 for d in results if d.geocoding_success)} geocoded successfully"
        )

        return results

    async def _ask_claude(
        self,
        country_code: str,
        country_name: str,
        count: int,
    ) -> List[SuggestedDestination]:
        """Call Claude AI to generate destination suggestions."""
        prompt = SUGGEST_PROMPT.format(
            country_name=country_name,
            country_code=country_code,
            count=count,
        )

        try:
            # Run synchronous Anthropic SDK call in a thread to avoid blocking
            response = await asyncio.to_thread(
                self.claude.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            # Extract text content
            raw_text = response.content[0].text.strip()

            # Parse JSON (handle potential markdown wrapping)
            if raw_text.startswith("```"):
                # Remove markdown code block
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            data = json.loads(raw_text)
            destinations_data = data.get("destinations", [])

            results = []
            for item in destinations_data:
                results.append(SuggestedDestination(
                    name=item["name"],
                    location_type=item.get("location_type", "city"),
                    description_fr=item.get("description_fr", ""),
                    description_en=item.get("description_en", ""),
                    sort_order=item.get("sort_order", len(results) + 1),
                    country_code=country_code,
                ))

            return results

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Raw response: {raw_text[:500]}")
            raise ValueError(f"Claude returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise

    async def _geocode_destination(
        self,
        dest: SuggestedDestination,
        country_code: str,
    ) -> SuggestedDestination:
        """Geocode a single destination using Google Maps."""
        try:
            # Build search query: "Destination Name, Country Name"
            country_name = get_country_name(country_code)
            search_query = f"{dest.name}, {country_name}"

            result = await self.maps.geocode(address=search_query, language="fr")

            if result:
                dest.lat = result.lat
                dest.lng = result.lng
                dest.google_place_id = result.place_id
                dest.formatted_address = result.formatted_address
                dest.geocoding_success = True
                logger.debug(f"Geocoded '{dest.name}': {result.lat}, {result.lng}")
            else:
                logger.warning(f"No geocoding result for '{dest.name}' in {country_name}")
                dest.geocoding_success = False

        except Exception as e:
            logger.warning(f"Geocoding error for '{dest.name}': {e}")
            dest.geocoding_success = False

        return dest


# ============================================================================
# Singleton
# ============================================================================

_suggester: Optional[DestinationSuggester] = None


def get_destination_suggester() -> DestinationSuggester:
    """Get the singleton DestinationSuggester instance."""
    global _suggester
    if _suggester is None:
        _suggester = DestinationSuggester()
    return _suggester
