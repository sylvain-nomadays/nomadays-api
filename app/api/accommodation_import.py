"""
Accommodation Import API - Extract hotel information from website URLs using AI.

This API allows importing accommodation data from hotel websites:
1. Fetch the webpage content
2. Extract accommodation information using AI (name, description, amenities, etc.)
3. Return structured data for pre-filling the accommodation form
"""

import json
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_current_tenant
from app.models.user import User
from app.models.tenant import Tenant
from app.config import get_settings

router = APIRouter(prefix="/accommodations/import", tags=["Accommodation Import"])

settings = get_settings()


# ============================================================================
# Schemas
# ============================================================================

class ImportFromUrlRequest(BaseModel):
    """Request to import accommodation data from URL."""
    url: HttpUrl


class ExtractedAccommodationData(BaseModel):
    """Extracted accommodation data from website."""
    name: Optional[str] = None
    description: Optional[str] = None
    star_rating: Optional[int] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    amenities: Optional[List[str]] = None
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website_url: Optional[str] = None
    # Room categories found
    room_categories: Optional[List[dict]] = None
    # Photos found (URLs)
    photo_urls: Optional[List[str]] = None
    # Extraction metadata
    source_url: str
    extraction_confidence: Optional[float] = None
    warnings: Optional[List[str]] = None


class ImportFromUrlResponse(BaseModel):
    """Response with extracted accommodation data."""
    success: bool
    data: Optional[ExtractedAccommodationData] = None
    error: Optional[str] = None


# ============================================================================
# AI Service
# ============================================================================

async def call_claude_api(prompt: str, system_prompt: str = "") -> str:
    """Call Claude API for text generation."""
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured (ANTHROPIC_API_KEY missing)",
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-3-haiku-20240307",  # Fast model for extraction
                "max_tokens": 4000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI service error: {response.text}",
            )

        data = response.json()
        return data["content"][0]["text"]


async def fetch_webpage(url: str) -> str:
    """Fetch webpage content with proper headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not fetch URL: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request error: {str(e)}",
            )


def extract_images_from_html(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Extract image URLs from HTML, filtering for likely hotel photos."""
    from urllib.parse import urljoin

    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            continue

        # Make absolute URL
        if not src.startswith("http"):
            src = urljoin(base_url, src)

        # Filter out icons, logos, etc. by checking size attributes or URL patterns
        width = img.get("width", "")
        height = img.get("height", "")

        # Skip small images (likely icons)
        try:
            if width and int(width) < 100:
                continue
            if height and int(height) < 100:
                continue
        except ValueError:
            pass

        # Skip common non-photo patterns
        skip_patterns = ["logo", "icon", "sprite", "avatar", "badge", "flag", "loading", "placeholder"]
        if any(p in src.lower() for p in skip_patterns):
            continue

        images.append(src)

    # Limit to first 10 images
    return images[:10]


async def extract_accommodation_from_html(html: str, url: str) -> ExtractedAccommodationData:
    """Use AI to extract accommodation information from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts, styles, etc.
    for tag in soup(["script", "style", "nav", "footer", "noscript", "iframe"]):
        tag.decompose()

    # Get text content
    text_content = soup.get_text(separator="\n", strip=True)

    # Limit content length
    text_content = text_content[:20000]

    # Extract images before cleaning
    photo_urls = extract_images_from_html(soup, url)

    prompt = f"""Analyse cette page web d'hôtel/hébergement et extrais UNIQUEMENT les informations EXPLICITEMENT présentes sur la page.

URL: {url}

Contenu de la page:
{text_content}

Extrais en JSON avec cette structure exacte:
{{
  "name": "Nom exact de l'hôtel tel qu'affiché sur la page",
  "description": "Reprendre la description existante sur le site, ne pas inventer",
  "star_rating": nombre d'étoiles (1-5) UNIQUEMENT si clairement indiqué sur la page, sinon null,
  "address": "Adresse EXACTE telle qu'écrite sur la page, sinon null",
  "city": "Ville UNIQUEMENT si explicitement mentionnée",
  "country_code": "Code pays ISO 2 lettres (ex: MA, TH, FR) déduit de l'adresse",
  "check_in_time": "HH:MM" UNIQUEMENT si indiqué sur la page, sinon null,
  "check_out_time": "HH:MM" UNIQUEMENT si indiqué sur la page, sinon null,
  "amenities": ["wifi", "piscine", ...] UNIQUEMENT les équipements clairement listés,
  "reservation_email": "email@hotel.com" UNIQUEMENT si affiché sur la page,
  "reservation_phone": "+XX XXX XXX XXX" UNIQUEMENT si affiché sur la page,
  "room_categories": [
    {{"name": "Nom exact de la catégorie", "description": "Description du site", "max_occupancy": nombre si indiqué}}
  ],
  "warnings": ["Liste des informations non trouvées ou incertaines"]
}}

RÈGLES STRICTES:
- NE PAS INVENTER d'informations. Si une donnée n'est pas sur la page, mettre null.
- NE PAS DEVINER l'adresse à partir du nom de l'hôtel.
- NE PAS REFORMULER la description, reprendre le texte existant DANS LA LANGUE ORIGINALE.
- NE PAS TRADUIRE. Si le site est en français, garder le texte en français. Si en anglais, garder en anglais.
- Pour les amenities, utilise UNIQUEMENT ces valeurs: wifi, piscine, spa, restaurant, parking, climatisation, salle_sport, bar, room_service, navette_aeroport, concierge, jardin, terrasse, animaux
- Ajouter dans warnings toutes les informations qui semblent manquer ou incertaines.
- Réponds UNIQUEMENT avec le JSON, sans commentaires."""

    system = """Tu es un assistant spécialisé dans l'extraction d'informations d'hôtels depuis des pages web.

RÈGLES FONDAMENTALES:
1. Tu extrais UNIQUEMENT les informations EXPLICITEMENT présentes sur la page.
2. Ne jamais inventer ou déduire des informations non présentes.
3. Si une information n'est pas trouvée, mettre null.
4. Préférer null plutôt que de deviner.
5. CONSERVER LA LANGUE ORIGINALE du site. Si le texte est en français, la description doit être en français. NE PAS TRADUIRE.

Réponds uniquement en JSON valide, sans commentaires ni markdown."""

    result = await call_claude_api(prompt, system)

    # Parse JSON response
    try:
        # Clean response (remove markdown code blocks if present)
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            # Remove first and last lines (code block markers)
            result = "\n".join(lines[1:-1])
        result = result.strip()

        data = json.loads(result)

        return ExtractedAccommodationData(
            name=data.get("name"),
            description=data.get("description"),
            star_rating=data.get("star_rating"),
            address=data.get("address"),
            city=data.get("city"),
            country_code=data.get("country_code"),
            check_in_time=data.get("check_in_time"),
            check_out_time=data.get("check_out_time"),
            amenities=data.get("amenities"),
            reservation_email=data.get("reservation_email"),
            reservation_phone=data.get("reservation_phone"),
            website_url=str(url),
            room_categories=data.get("room_categories"),
            photo_urls=photo_urls if photo_urls else None,
            source_url=str(url),
            extraction_confidence=0.8 if data.get("name") and data.get("description") else 0.5,
            warnings=data.get("warnings"),
        )
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract accommodation data: {str(e)}",
        )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/from-url", response_model=ImportFromUrlResponse)
async def import_from_url(
    request: ImportFromUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Import accommodation data from a hotel website URL.

    This endpoint:
    1. Fetches the webpage content
    2. Uses AI to extract hotel information
    3. Returns structured data for pre-filling the accommodation form

    The returned data can be used to create or update an accommodation.
    """
    try:
        # Fetch webpage
        html = await fetch_webpage(str(request.url))

        # Extract data using AI
        extracted_data = await extract_accommodation_from_html(html, str(request.url))

        return ImportFromUrlResponse(
            success=True,
            data=extracted_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        return ImportFromUrlResponse(
            success=False,
            error=str(e),
        )
