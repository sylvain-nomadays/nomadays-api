"""
Trip Preview API - Translation preview with caching.

Provides endpoints for previewing a trip in another language
using cached translations to avoid regenerating on each request.
"""

import hashlib
import json
from datetime import datetime
from typing import Optional, Literal, List, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import Trip, TripDay
from app.models.trip_translation_cache import TripTranslationCache
from app.config import get_settings

router = APIRouter()
settings = get_settings()

# Supported languages
SUPPORTED_LANGUAGES = {
    "fr": {"name": "Français", "flag": "🇫🇷"},
    "en": {"name": "English", "flag": "🇬🇧"},
    "es": {"name": "Español", "flag": "🇪🇸"},
    "de": {"name": "Deutsch", "flag": "🇩🇪"},
    "it": {"name": "Italiano", "flag": "🇮🇹"},
    "pt": {"name": "Português", "flag": "🇵🇹"},
    "nl": {"name": "Nederlands", "flag": "🇳🇱"},
    "ru": {"name": "Русский", "flag": "🇷🇺"},
    "zh": {"name": "中文", "flag": "🇨🇳"},
    "ja": {"name": "日本語", "flag": "🇯🇵"},
}

LanguageCode = Literal["fr", "en", "es", "de", "it", "pt", "nl", "ru", "zh", "ja"]


# ============== Schemas ==============

class TranslatedDay(BaseModel):
    day_number: int
    title: Optional[str] = None
    description: Optional[str] = None


class TranslationContent(BaseModel):
    """Translated content of a trip."""
    name: Optional[str] = None
    description_short: Optional[str] = None
    highlights: Optional[List[Any]] = None
    inclusions: Optional[List[Any]] = None
    exclusions: Optional[List[Any]] = None
    info_general: Optional[str] = None
    info_formalities: Optional[str] = None
    info_booking_conditions: Optional[str] = None
    info_cancellation_policy: Optional[str] = None
    info_additional: Optional[str] = None
    days: Optional[List[TranslatedDay]] = None


class CacheMetadata(BaseModel):
    """Metadata about the translation cache."""
    cached_at: Optional[datetime] = None
    cache_age_minutes: int = 0
    is_stale: bool = False
    stale_reason: Optional[str] = None
    exists: bool = False


class PreviewResponse(BaseModel):
    """Response for translation preview."""
    trip_id: int
    language: str
    language_name: str
    language_flag: str
    content: TranslationContent
    cache_metadata: CacheMetadata


class LanguageStatus(BaseModel):
    """Status of a language for a trip."""
    code: str
    name: str
    flag: str
    has_cache: bool = False
    is_stale: bool = False
    cached_at: Optional[datetime] = None
    has_independent_copy: bool = False
    independent_copy_id: Optional[int] = None


class LanguagesResponse(BaseModel):
    """Response listing all languages and their status."""
    trip_id: int
    source_language: str
    languages: List[LanguageStatus]


# ============== Helpers ==============

def compute_source_hash(trip: Trip) -> str:
    """Compute a hash of the translatable content to detect changes."""
    content = {
        "name": trip.name,
        "description_short": trip.description_short,
        "highlights": trip.highlights,
        "inclusions": trip.inclusions,
        "exclusions": trip.exclusions,
        "info_general": trip.info_general,
        "info_formalities": trip.info_formalities,
        "info_booking_conditions": trip.info_booking_conditions,
        "info_cancellation_policy": trip.info_cancellation_policy,
        "info_additional": trip.info_additional,
        "days": [
            {"day_number": d.day_number, "title": d.title, "description": d.description}
            for d in sorted(trip.days, key=lambda x: x.day_number)
        ] if trip.days else [],
    }
    content_str = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(content_str.encode()).hexdigest()


async def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text using Claude API."""
    if not text or not text.strip():
        return text

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        source_name = SUPPORTED_LANGUAGES.get(source_lang, {}).get("name", source_lang)
        target_name = SUPPORTED_LANGUAGES.get(target_lang, {}).get("name", target_lang)

        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            system=f"Tu es un traducteur professionnel spécialisé dans le tourisme. Traduis du {source_name} vers le {target_name}. Garde le même ton et style. Réponds uniquement avec la traduction, sans commentaires.",
            messages=[
                {"role": "user", "content": text}
            ],
        )

        return message.content[0].text.strip()
    except Exception as e:
        print(f"Translation error: {e}")
        return text


async def generate_translation(trip: Trip, target_lang: str) -> TranslationContent:
    """Generate translation for a trip's content."""
    source_lang = trip.language or "fr"

    content = TranslationContent()

    # Name
    content.name = await translate_text(trip.name, source_lang, target_lang)

    # Description
    if trip.description_short:
        content.description_short = await translate_text(trip.description_short, source_lang, target_lang)

    # Highlights
    if trip.highlights:
        translated_highlights = []
        for h in trip.highlights:
            title = await translate_text(h.get("title", ""), source_lang, target_lang)
            translated_highlights.append({"title": title, "icon": h.get("icon")})
        content.highlights = translated_highlights

    # Inclusions
    if trip.inclusions:
        translated_inclusions = []
        for item in trip.inclusions:
            text = await translate_text(item.get("text", ""), source_lang, target_lang)
            translated_inclusions.append({"text": text, "default": item.get("default", False)})
        content.inclusions = translated_inclusions

    # Exclusions
    if trip.exclusions:
        translated_exclusions = []
        for item in trip.exclusions:
            text = await translate_text(item.get("text", ""), source_lang, target_lang)
            translated_exclusions.append({"text": text, "default": item.get("default", False)})
        content.exclusions = translated_exclusions

    # Info fields
    if trip.info_general:
        content.info_general = await translate_text(trip.info_general, source_lang, target_lang)
    if trip.info_formalities:
        content.info_formalities = await translate_text(trip.info_formalities, source_lang, target_lang)
    if trip.info_booking_conditions:
        content.info_booking_conditions = await translate_text(trip.info_booking_conditions, source_lang, target_lang)
    if trip.info_cancellation_policy:
        content.info_cancellation_policy = await translate_text(trip.info_cancellation_policy, source_lang, target_lang)
    if trip.info_additional:
        content.info_additional = await translate_text(trip.info_additional, source_lang, target_lang)

    # Days
    if trip.days:
        translated_days = []
        for day in sorted(trip.days, key=lambda x: x.day_number):
            translated_day = TranslatedDay(day_number=day.day_number)
            if day.title:
                translated_day.title = await translate_text(day.title, source_lang, target_lang)
            if day.description:
                translated_day.description = await translate_text(day.description, source_lang, target_lang)
            translated_days.append(translated_day)
        content.days = translated_days

    return content


# ============== Endpoints ==============

@router.get("/{trip_id}/languages", response_model=LanguagesResponse)
async def get_trip_languages(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get the status of all languages for a trip.
    Shows which languages have cached translations and which have independent copies.
    """
    # Get the trip
    query = select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    result = await db.execute(query)
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Circuit not found")

    # Get all caches for this trip
    caches_query = select(TripTranslationCache).where(TripTranslationCache.trip_id == trip_id)
    caches_result = await db.execute(caches_query)
    caches = {c.language: c for c in caches_result.scalars().all()}

    # Get all independent translations
    translations_query = select(Trip).where(
        Trip.source_trip_id == trip_id,
        Trip.tenant_id == tenant.id,
    )
    translations_result = await db.execute(translations_query)
    translations = {t.language: t for t in translations_result.scalars().all()}

    # Build language status list
    languages = []
    for code, info in SUPPORTED_LANGUAGES.items():
        lang_status = LanguageStatus(
            code=code,
            name=info["name"],
            flag=info["flag"],
        )

        # Check cache
        if code in caches:
            cache = caches[code]
            lang_status.has_cache = True
            lang_status.is_stale = cache.is_stale
            lang_status.cached_at = cache.cached_at

        # Check independent copy
        if code in translations:
            lang_status.has_independent_copy = True
            lang_status.independent_copy_id = translations[code].id

        languages.append(lang_status)

    return LanguagesResponse(
        trip_id=trip_id,
        source_language=trip.language or "fr",
        languages=languages,
    )


@router.get("/{trip_id}/preview/{language}", response_model=PreviewResponse)
async def get_preview(
    trip_id: int,
    language: LanguageCode,
    db: DbSession,
    tenant: CurrentTenant,
    force_refresh: bool = False,
):
    """
    Get a preview of the trip in the specified language.

    If a cached translation exists and is not stale, returns it.
    Otherwise generates a new translation and caches it.

    Query params:
    - force_refresh: If true, regenerate the translation even if cache exists
    """
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")

    # Get the trip with days
    query = (
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(selectinload(Trip.days))
    )
    result = await db.execute(query)
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Circuit not found")

    # If requesting the same language as source, return original content
    if language == (trip.language or "fr"):
        return PreviewResponse(
            trip_id=trip_id,
            language=language,
            language_name=SUPPORTED_LANGUAGES[language]["name"],
            language_flag=SUPPORTED_LANGUAGES[language]["flag"],
            content=TranslationContent(
                name=trip.name,
                description_short=trip.description_short,
                highlights=trip.highlights,
                inclusions=trip.inclusions,
                exclusions=trip.exclusions,
                info_general=trip.info_general,
                info_formalities=trip.info_formalities,
                info_booking_conditions=trip.info_booking_conditions,
                info_cancellation_policy=trip.info_cancellation_policy,
                info_additional=trip.info_additional,
                days=[
                    TranslatedDay(day_number=d.day_number, title=d.title, description=d.description)
                    for d in sorted(trip.days, key=lambda x: x.day_number)
                ] if trip.days else None,
            ),
            cache_metadata=CacheMetadata(exists=False, is_stale=False),
        )

    # Compute current source hash
    current_hash = compute_source_hash(trip)

    # Check for existing cache
    cache_query = select(TripTranslationCache).where(
        TripTranslationCache.trip_id == trip_id,
        TripTranslationCache.language == language,
    )
    cache_result = await db.execute(cache_query)
    cache = cache_result.scalar_one_or_none()

    # Check if we need to (re)generate
    needs_generation = (
        force_refresh
        or cache is None
        or (cache and cache.is_stale)
    )

    if needs_generation:
        # Generate new translation
        content = await generate_translation(trip, language)

        if cache:
            # Update existing cache
            cache.name = content.name
            cache.description_short = content.description_short
            cache.highlights = content.highlights
            cache.inclusions = content.inclusions
            cache.exclusions = content.exclusions
            cache.info_general = content.info_general
            cache.info_formalities = content.info_formalities
            cache.info_booking_conditions = content.info_booking_conditions
            cache.info_cancellation_policy = content.info_cancellation_policy
            cache.info_additional = content.info_additional
            cache.translated_days = [d.model_dump() for d in content.days] if content.days else None
            cache.cached_at = datetime.utcnow()
            cache.source_hash = current_hash
            cache.is_stale = False
        else:
            # Create new cache
            cache = TripTranslationCache(
                tenant_id=tenant.id,
                trip_id=trip_id,
                language=language,
                name=content.name,
                description_short=content.description_short,
                highlights=content.highlights,
                inclusions=content.inclusions,
                exclusions=content.exclusions,
                info_general=content.info_general,
                info_formalities=content.info_formalities,
                info_booking_conditions=content.info_booking_conditions,
                info_cancellation_policy=content.info_cancellation_policy,
                info_additional=content.info_additional,
                translated_days=[d.model_dump() for d in content.days] if content.days else None,
                cached_at=datetime.utcnow(),
                source_hash=current_hash,
                is_stale=False,
            )
            db.add(cache)

        await db.commit()
        await db.refresh(cache)

        cache_metadata = CacheMetadata(
            cached_at=cache.cached_at,
            cache_age_minutes=0,
            is_stale=False,
            exists=True,
        )
    else:
        # Use existing cache
        content = TranslationContent(
            name=cache.name,
            description_short=cache.description_short,
            highlights=cache.highlights,
            inclusions=cache.inclusions,
            exclusions=cache.exclusions,
            info_general=cache.info_general,
            info_formalities=cache.info_formalities,
            info_booking_conditions=cache.info_booking_conditions,
            info_cancellation_policy=cache.info_cancellation_policy,
            info_additional=cache.info_additional,
            days=[TranslatedDay(**d) for d in cache.translated_days] if cache.translated_days else None,
        )

        # Check if stale (hash mismatch)
        is_stale = cache.source_hash != current_hash
        if is_stale and not cache.is_stale:
            # Mark as stale in DB
            cache.is_stale = True
            await db.commit()

        cache_age_minutes = int((datetime.utcnow() - cache.cached_at).total_seconds() / 60) if cache.cached_at else 0

        cache_metadata = CacheMetadata(
            cached_at=cache.cached_at,
            cache_age_minutes=cache_age_minutes,
            is_stale=is_stale,
            stale_reason="Le contenu original a été modifié depuis la dernière traduction." if is_stale else None,
            exists=True,
        )

    return PreviewResponse(
        trip_id=trip_id,
        language=language,
        language_name=SUPPORTED_LANGUAGES[language]["name"],
        language_flag=SUPPORTED_LANGUAGES[language]["flag"],
        content=content,
        cache_metadata=cache_metadata,
    )


@router.post("/{trip_id}/preview/{language}/refresh", response_model=PreviewResponse)
async def refresh_preview(
    trip_id: int,
    language: LanguageCode,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Force regeneration of the translation cache for a specific language.
    """
    return await get_preview(
        trip_id=trip_id,
        language=language,
        db=db,
        tenant=tenant,
        force_refresh=True,
    )
