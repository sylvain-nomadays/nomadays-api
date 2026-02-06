"""
Circuit Import API - Scrape and rewrite circuits from external URLs using AI

This API allows importing circuits from DMC partner websites:
1. Fetch the webpage content
2. Extract circuit information using AI
3. Rewrite the content in 4 different tones
4. Create a new circuit with the extracted data
"""

from datetime import datetime
from typing import List, Optional, Literal
import httpx
from bs4 import BeautifulSoup

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_tenant_id
from app.models.trip import Trip, TripDay
from app.models.user import User
from app.config import get_settings
import uuid

router = APIRouter(prefix="/import", tags=["Circuit Import"])

settings = get_settings()

# Tone options for rewriting
ToneType = Literal["marketing_emotionnel", "aventure", "familial", "factuel"]


# ============================================================================
# Schemas
# ============================================================================

class ImportRequest(BaseModel):
    """Request to import a circuit from URL."""
    url: HttpUrl
    tone: ToneType = "factuel"


class ExtractedDay(BaseModel):
    """Extracted day from source."""
    day_number: int
    title: Optional[str] = None
    description: Optional[str] = None
    locations: Optional[str] = None


class ExtractedCircuit(BaseModel):
    """Extracted circuit data from URL."""
    name: str
    destination_country: Optional[str]
    duration_days: int
    description_short: Optional[str]
    highlights: Optional[List[str]]
    inclusions: Optional[List[str]]
    exclusions: Optional[List[str]]
    days: List[ExtractedDay]


class RewrittenCircuit(BaseModel):
    """Circuit with AI-rewritten content."""
    original: ExtractedCircuit
    rewritten_name: str
    rewritten_description: str
    rewritten_highlights: List[str]
    rewritten_days: List[ExtractedDay]
    tone: ToneType


class ImportPreviewResponse(BaseModel):
    """Preview of imported circuit before creation."""
    source_url: str
    extracted: ExtractedCircuit
    versions: dict  # {tone: RewrittenCircuit}


class ImportCreateRequest(BaseModel):
    """Request to create circuit from imported data."""
    source_url: str
    name: str
    tone: ToneType
    description_short: str
    highlights: List[str]
    days: List[ExtractedDay]
    destination_country: Optional[str]
    duration_days: int
    inclusions: Optional[List[str]]
    exclusions: Optional[List[str]]
    type: str = "online"


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
                "model": "claude-3-haiku-20240307",  # Fast model for rewriting
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


async def extract_circuit_from_html(html: str, url: str) -> ExtractedCircuit:
    """Use AI to extract circuit information from HTML."""
    # First, clean the HTML
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts, styles, etc.
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Get text content
    text_content = soup.get_text(separator="\n", strip=True)

    # Limit content length
    text_content = text_content[:15000]

    prompt = f"""Analyse cette page web de circuit de voyage et extrais les informations suivantes en JSON:

URL: {url}

Contenu de la page:
{text_content}

Extrais en JSON avec cette structure exacte:
{{
  "name": "Nom du circuit",
  "destination_country": "Code pays ISO 2 lettres (ex: TH, VN, JP)",
  "duration_days": nombre de jours,
  "description_short": "Description courte du circuit (2-3 phrases)",
  "highlights": ["Point fort 1", "Point fort 2", ...],
  "inclusions": ["Ce qui est inclus 1", ...],
  "exclusions": ["Ce qui n'est pas inclus 1", ...],
  "days": [
    {{"day_number": 1, "title": "Titre jour 1", "description": "Description", "locations": "Ville A - Ville B"}},
    ...
  ]
}}

Réponds UNIQUEMENT avec le JSON, sans commentaires."""

    system = "Tu es un assistant qui extrait des informations structurées de pages web de voyages. Réponds uniquement en JSON valide."

    result = await call_claude_api(prompt, system)

    # Parse JSON response
    import json
    try:
        # Clean response (remove markdown code blocks if present)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        result = result.strip()

        data = json.loads(result)
        return ExtractedCircuit(**data)
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract circuit data: {str(e)}",
        )


async def rewrite_circuit(circuit: ExtractedCircuit, tone: ToneType) -> RewrittenCircuit:
    """Rewrite circuit content in the specified tone."""
    tone_descriptions = {
        "marketing_emotionnel": "émotionnel et inspirant, qui fait rêver, utilise des adjectifs évocateurs et crée de l'envie",
        "aventure": "aventurier et exploratoire, qui met en avant l'exploration, la découverte et les expériences uniques",
        "familial": "familial et rassurant, adapté aux familles avec enfants, mettant en avant la sécurité et le confort",
        "factuel": "factuel et informatif, clair et précis, sans fioritures, axé sur les informations pratiques",
    }

    prompt = f"""Réécris ce circuit de voyage avec un ton {tone_descriptions[tone]}.

Circuit original:
- Nom: {circuit.name}
- Description: {circuit.description_short}
- Points forts: {', '.join(circuit.highlights or [])}
- Programme jour par jour:
{chr(10).join([f"Jour {d.day_number}: {d.title} - {d.description}" for d in circuit.days])}

Réécris en JSON avec cette structure:
{{
  "name": "Nouveau nom accrocheur",
  "description": "Nouvelle description (5-7 lignes)",
  "highlights": ["5 points forts réécrits"],
  "days": [
    {{"day_number": 1, "title": "Nouveau titre", "description": "Nouvelle description du jour"}}
  ]
}}

Garde la même structure de jours mais réécris tout le contenu avec le ton demandé.
Réponds UNIQUEMENT avec le JSON."""

    system = f"Tu es un rédacteur de voyages expert. Ton style est {tone_descriptions[tone]}. Réponds uniquement en JSON valide."

    result = await call_claude_api(prompt, system)

    # Parse JSON response
    import json
    try:
        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        result = result.strip()

        data = json.loads(result)

        return RewrittenCircuit(
            original=circuit,
            rewritten_name=data["name"],
            rewritten_description=data["description"],
            rewritten_highlights=data["highlights"],
            rewritten_days=[ExtractedDay(**d) for d in data["days"]],
            tone=tone,
        )
    except (json.JSONDecodeError, KeyError) as e:
        # Return original if rewriting fails
        return RewrittenCircuit(
            original=circuit,
            rewritten_name=circuit.name,
            rewritten_description=circuit.description_short or "",
            rewritten_highlights=circuit.highlights or [],
            rewritten_days=circuit.days,
            tone=tone,
        )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    request: ImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Preview a circuit import from URL.

    Fetches the URL, extracts circuit data, and rewrites it in all 4 tones.
    Returns the original and all rewritten versions for selection.
    """
    # Fetch the URL
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                str(request.url),
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; NomaydaysBot/1.0)",
                }
            )
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch URL: {str(e)}",
        )

    # Extract circuit data
    extracted = await extract_circuit_from_html(html, str(request.url))

    # Rewrite in all tones
    versions = {}
    for tone in ["marketing_emotionnel", "aventure", "familial", "factuel"]:
        versions[tone] = await rewrite_circuit(extracted, tone)

    return ImportPreviewResponse(
        source_url=str(request.url),
        extracted=extracted,
        versions={k: v.model_dump() for k, v in versions.items()},
    )


@router.post("/extract")
async def extract_only(
    request: ImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Extract circuit data from URL without rewriting.
    Faster than preview - useful for quick extraction.
    """
    # Fetch the URL
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                str(request.url),
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; NomaydaysBot/1.0)",
                }
            )
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch URL: {str(e)}",
        )

    # Extract circuit data
    extracted = await extract_circuit_from_html(html, str(request.url))

    return {
        "source_url": str(request.url),
        "extracted": extracted,
    }


@router.post("/rewrite")
async def rewrite_content(
    circuit: ExtractedCircuit,
    tone: ToneType = "factuel",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Rewrite extracted circuit content in a specific tone.
    """
    rewritten = await rewrite_circuit(circuit, tone)
    return rewritten


@router.post("/create")
async def create_from_import(
    request: ImportCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """
    Create a new circuit from imported data.
    """
    # Create the trip
    trip = Trip(
        tenant_id=tenant_id,
        name=request.name,
        type=request.type,
        destination_country=request.destination_country,
        duration_days=request.duration_days,
        description_short=request.description_short,
        description_tone=request.tone,
        highlights=[{"title": h} for h in request.highlights],
        inclusions=[{"text": i} for i in (request.inclusions or [])],
        exclusions=[{"text": e} for e in (request.exclusions or [])],
        source_url=request.source_url,
        source_imported_at=datetime.utcnow(),
        status="draft",
        created_by_id=user.id,
    )
    db.add(trip)
    await db.flush()  # Get trip.id

    # Create days
    for day_data in request.days:
        day = TripDay(
            tenant_id=tenant_id,
            trip_id=trip.id,
            day_number=day_data.day_number,
            title=day_data.title,
            description=day_data.description,
            location_from=day_data.locations.split(" - ")[0] if day_data.locations and " - " in day_data.locations else day_data.locations,
            location_to=day_data.locations.split(" - ")[-1] if day_data.locations and " - " in day_data.locations else None,
            sort_order=day_data.day_number,
        )
        db.add(day)

    await db.commit()
    await db.refresh(trip)

    return {
        "id": trip.id,
        "name": trip.name,
        "message": "Circuit importé avec succès",
    }
