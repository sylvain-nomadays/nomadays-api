"""
Circuit translation endpoint.
Translates a circuit into another language using AI.
"""

import json
from typing import Optional, Literal
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import Trip, TripDay
from app.config import get_settings

router = APIRouter()

settings = get_settings()


# Supported languages
SUPPORTED_LANGUAGES = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ru": "Русский",
    "zh": "中文",
    "ja": "日本語",
}

LanguageCode = Literal["fr", "en", "es", "de", "it", "pt", "nl", "ru", "zh", "ja"]


class TranslateRequest(BaseModel):
    target_language: LanguageCode


class TranslateResponse(BaseModel):
    id: int
    name: str
    language: str
    source_trip_id: int
    message: str


async def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text using Claude API."""
    if not text or not text.strip():
        return text

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        source_name = SUPPORTED_LANGUAGES.get(source_lang, source_lang)
        target_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)

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
        return text  # Return original if translation fails


async def translate_circuit_content(
    trip: Trip,
    target_lang: str,
) -> dict:
    """
    Translate all translatable content of a circuit.
    Returns a dict with translated fields.
    """
    source_lang = trip.language or "fr"

    # Collect all texts to translate in a batch for efficiency
    translations = {}

    # Name
    translations["name"] = await translate_text(trip.name, source_lang, target_lang)

    # Description
    if trip.description_short:
        translations["description_short"] = await translate_text(
            trip.description_short, source_lang, target_lang
        )

    # Highlights
    if trip.highlights:
        translated_highlights = []
        for h in trip.highlights:
            title = await translate_text(h.get("title", ""), source_lang, target_lang)
            translated_highlights.append({"title": title, "icon": h.get("icon")})
        translations["highlights"] = translated_highlights

    # Inclusions
    if trip.inclusions:
        translated_inclusions = []
        for item in trip.inclusions:
            text = await translate_text(item.get("text", ""), source_lang, target_lang)
            translated_inclusions.append({"text": text, "default": item.get("default", False)})
        translations["inclusions"] = translated_inclusions

    # Exclusions
    if trip.exclusions:
        translated_exclusions = []
        for item in trip.exclusions:
            text = await translate_text(item.get("text", ""), source_lang, target_lang)
            translated_exclusions.append({"text": text, "default": item.get("default", False)})
        translations["exclusions"] = translated_exclusions

    # Info fields
    if trip.info_general:
        translations["info_general"] = await translate_text(
            trip.info_general, source_lang, target_lang
        )
    if trip.info_formalities:
        translations["info_formalities"] = await translate_text(
            trip.info_formalities, source_lang, target_lang
        )
    if trip.info_booking_conditions:
        translations["info_booking_conditions"] = await translate_text(
            trip.info_booking_conditions, source_lang, target_lang
        )
    if trip.info_cancellation_policy:
        translations["info_cancellation_policy"] = await translate_text(
            trip.info_cancellation_policy, source_lang, target_lang
        )
    if trip.info_additional:
        translations["info_additional"] = await translate_text(
            trip.info_additional, source_lang, target_lang
        )

    # Days
    translated_days = []
    for day in trip.days:
        translated_day = {
            "day_number": day.day_number,
            "sort_order": day.sort_order,
            "location_from": day.location_from,
            "location_to": day.location_to,
        }
        if day.title:
            translated_day["title"] = await translate_text(day.title, source_lang, target_lang)
        if day.description:
            translated_day["description"] = await translate_text(day.description, source_lang, target_lang)
        translated_days.append(translated_day)
    translations["days"] = translated_days

    return translations


@router.get("/languages")
async def list_languages():
    """List supported languages for translation."""
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in SUPPORTED_LANGUAGES.items()
        ]
    }


@router.post("/{trip_id}/translate", response_model=TranslateResponse)
async def translate_circuit(
    trip_id: int,
    request: TranslateRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Translate a circuit into another language.
    Creates a new independent circuit with the translated content.
    """
    # Get the source trip
    query = (
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(selectinload(Trip.days))
    )
    result = await db.execute(query)
    source_trip = result.scalar_one_or_none()

    if not source_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Circuit not found",
        )

    target_lang = request.target_language

    # Check if already translated to this language
    existing_query = select(Trip).where(
        Trip.source_trip_id == trip_id,
        Trip.language == target_lang,
        Trip.tenant_id == tenant.id,
    )
    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A translation to {SUPPORTED_LANGUAGES[target_lang]} already exists (ID: {existing.id})",
        )

    # Translate the content
    translated = await translate_circuit_content(source_trip, target_lang)

    # Create the new translated trip
    new_trip = Trip(
        tenant_id=tenant.id,
        name=translated.get("name", source_trip.name),
        type=source_trip.type,
        master_trip_id=source_trip.master_trip_id,
        is_published=False,  # Not published by default
        duration_days=source_trip.duration_days,
        destination_country=source_trip.destination_country,
        destination_countries=source_trip.destination_countries,
        default_currency=source_trip.default_currency,
        margin_pct=source_trip.margin_pct,
        margin_type=source_trip.margin_type,
        vat_pct=source_trip.vat_pct,
        vat_calculation_mode=source_trip.vat_calculation_mode,
        comfort_level=source_trip.comfort_level,
        difficulty_level=source_trip.difficulty_level,
        # Translated content
        description_short=translated.get("description_short"),
        description_tone=source_trip.description_tone,
        highlights=translated.get("highlights"),
        inclusions=translated.get("inclusions"),
        exclusions=translated.get("exclusions"),
        info_general=translated.get("info_general"),
        info_formalities=translated.get("info_formalities"),
        info_booking_conditions=translated.get("info_booking_conditions"),
        info_cancellation_policy=translated.get("info_cancellation_policy"),
        info_additional=translated.get("info_additional"),
        # Language tracking
        language=target_lang,
        source_trip_id=source_trip.id,
        # Keep source URL if any
        source_url=source_trip.source_url,
        # Ownership
        created_by_id=user.id,
        status="draft",
    )

    db.add(new_trip)
    await db.flush()

    # Create translated days
    for day_data in translated.get("days", []):
        new_day = TripDay(
            tenant_id=tenant.id,
            trip_id=new_trip.id,
            day_number=day_data["day_number"],
            day_number_end=day_data.get("day_number_end"),
            title=day_data.get("title"),
            description=day_data.get("description"),
            location_from=day_data.get("location_from"),
            location_to=day_data.get("location_to"),
            sort_order=day_data.get("sort_order", 0),
        )
        db.add(new_day)

    await db.commit()
    await db.refresh(new_trip)

    return TranslateResponse(
        id=new_trip.id,
        name=new_trip.name,
        language=new_trip.language,
        source_trip_id=source_trip.id,
        message=f"Circuit traduit en {SUPPORTED_LANGUAGES[target_lang]} avec succès",
    )


@router.get("/{trip_id}/translations")
async def list_translations(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all translations of a circuit.
    """
    # Get the source trip (or the original if this is already a translation)
    query = select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    result = await db.execute(query)
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Circuit not found",
        )

    # If this trip is a translation, get the original
    original_id = trip.source_trip_id if trip.source_trip_id else trip.id

    # Get all translations including the original
    translations_query = select(Trip).where(
        Trip.tenant_id == tenant.id,
        (Trip.id == original_id) | (Trip.source_trip_id == original_id),
    )
    translations = (await db.execute(translations_query)).scalars().all()

    return {
        "original_id": original_id,
        "translations": [
            {
                "id": t.id,
                "name": t.name,
                "language": t.language,
                "language_name": SUPPORTED_LANGUAGES.get(t.language, t.language),
                "is_original": t.id == original_id,
                "status": t.status,
            }
            for t in translations
        ],
    }


class PushTranslationRequest(BaseModel):
    target_trip_ids: list[int]


class PushTranslationResult(BaseModel):
    trip_id: int
    language: str
    success: bool
    message: str


class PushTranslationResponse(BaseModel):
    source_trip_id: int
    results: list[PushTranslationResult]


@router.post("/{trip_id}/push")
async def push_translation(
    trip_id: int,
    request: PushTranslationRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Push content from source trip to target translated trips.
    Re-translates the content from source language to each target language.
    """
    # Get the source trip
    query = (
        select(Trip)
        .where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
        .options(selectinload(Trip.days))
    )
    result = await db.execute(query)
    source_trip = result.scalar_one_or_none()

    if not source_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source circuit not found",
        )

    results = []

    for target_id in request.target_trip_ids:
        try:
            # Get the target trip
            target_query = (
                select(Trip)
                .where(Trip.id == target_id, Trip.tenant_id == tenant.id)
                .options(selectinload(Trip.days))
            )
            target_result = await db.execute(target_query)
            target_trip = target_result.scalar_one_or_none()

            if not target_trip:
                results.append(PushTranslationResult(
                    trip_id=target_id,
                    language="unknown",
                    success=False,
                    message="Circuit cible non trouvé",
                ))
                continue

            target_lang = target_trip.language or "fr"

            # Skip if same language
            if target_lang == (source_trip.language or "fr"):
                results.append(PushTranslationResult(
                    trip_id=target_id,
                    language=target_lang,
                    success=False,
                    message="Même langue que la source",
                ))
                continue

            # Translate content
            translated = await translate_circuit_content(source_trip, target_lang)

            # Update target trip with translated content
            target_trip.name = translated.get("name", source_trip.name)
            target_trip.description_short = translated.get("description_short")
            target_trip.highlights = translated.get("highlights")
            target_trip.inclusions = translated.get("inclusions")
            target_trip.exclusions = translated.get("exclusions")
            target_trip.info_general = translated.get("info_general")
            target_trip.info_formalities = translated.get("info_formalities")
            target_trip.info_booking_conditions = translated.get("info_booking_conditions")
            target_trip.info_cancellation_policy = translated.get("info_cancellation_policy")
            target_trip.info_additional = translated.get("info_additional")

            # Update days
            translated_days = translated.get("days", [])
            for day_data in translated_days:
                # Find matching day in target
                target_day = next(
                    (d for d in target_trip.days if d.day_number == day_data["day_number"]),
                    None
                )
                if target_day:
                    target_day.title = day_data.get("title")
                    target_day.description = day_data.get("description")

            results.append(PushTranslationResult(
                trip_id=target_id,
                language=target_lang,
                success=True,
                message=f"Traduit en {SUPPORTED_LANGUAGES.get(target_lang, target_lang)}",
            ))

        except Exception as e:
            print(f"Error pushing to trip {target_id}: {e}")
            results.append(PushTranslationResult(
                trip_id=target_id,
                language="unknown",
                success=False,
                message=str(e),
            ))

    await db.commit()

    return PushTranslationResponse(
        source_trip_id=trip_id,
        results=results,
    )
