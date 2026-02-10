"""
Circuit Image Generator — Orchestrateur principal.

Analyse les descriptifs jour par jour d'un circuit, génère des prompts
optimisés, appelle Vertex AI (Imagen 3), traite les images (AVIF/WebP/LQIP),
et les stocke sous une nomenclature SEO-friendly :
  Destination / Type / Attraction / nom-seo-friendly.avif

Workflow:
1. Charger le circuit et ses jours
2. Pour chaque jour, analyser le descriptif et extraire les attractions
3. Générer un prompt optimisé pour chaque attraction
4. Appeler Vertex AI pour générer l'image
5. Traiter l'image (resize, AVIF, WebP, LQIP)
6. Uploader vers Supabase Storage avec nomenclature SEO
7. Créer les enregistrements TripPhoto en BDD
"""

import re
import json
import logging
import unicodedata
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trip import Trip, TripDay
from app.models.trip_photo import TripPhoto
from app.services.vertex_ai import ImageGenerationService, get_image_generation_service
from app.services.image_processor import (
    process_image,
    ProcessedVariant,
    generate_lqip,
    SIZES,
)
from app.services.storage import get_supabase_client, BUCKET_NAME

logger = logging.getLogger(__name__)


# ============================================================================
# Country code → destination name mapping
# ============================================================================

COUNTRY_DESTINATIONS = {
    "TH": "thailand",
    "VN": "vietnam",
    "KH": "cambodia",
    "LA": "laos",
    "MM": "myanmar",
    "ID": "indonesia",
    "MY": "malaysia",
    "PH": "philippines",
    "SG": "singapore",
    "JP": "japan",
    "KR": "south-korea",
    "CN": "china",
    "IN": "india",
    "NP": "nepal",
    "LK": "sri-lanka",
    "MV": "maldives",
    "BT": "bhutan",
    "MN": "mongolia",
    "UZ": "uzbekistan",
    "GE": "georgia",
    "AM": "armenia",
    "TR": "turkey",
    "MA": "morocco",
    "TZ": "tanzania",
    "KE": "kenya",
    "MG": "madagascar",
    "ZA": "south-africa",
    "PE": "peru",
    "BO": "bolivia",
    "CO": "colombia",
    "CR": "costa-rica",
    "MX": "mexico",
    "CU": "cuba",
    "BR": "brazil",
    "AR": "argentina",
    "CL": "chile",
    "EC": "ecuador",
    "IT": "italy",
    "ES": "spain",
    "PT": "portugal",
    "GR": "greece",
    "HR": "croatia",
    "IS": "iceland",
    "NO": "norway",
}


# ============================================================================
# Scene type mapping — analyse automatique du contenu
# ============================================================================

SCENE_KEYWORDS = {
    "temple": {
        "keywords": ["temple", "pagode", "wat ", "bouddha", "buddha", "monastère", "stupa", "sanctuaire", "shrine"],
        "scene_type": "ancient temple, sacred Buddhist architecture, golden spires",
        "style": "cinematic",
        "time_of_day": "golden hour",
        "attraction_type": "attraction",
    },
    "beach": {
        "keywords": ["plage", "beach", "île", "island", "baie", "bay", "côte", "coast", "mer", "snorkeling", "plongée"],
        "scene_type": "pristine tropical beach, turquoise water, white sand",
        "style": "photorealistic",
        "time_of_day": "sunrise",
        "attraction_type": "destination",
    },
    "mountain": {
        "keywords": ["montagne", "mountain", "trek", "trekking", "randonnée", "sommet", "col ", "pass", "altitude", "volcan", "volcano"],
        "scene_type": "majestic mountain landscape, panoramic vista, misty peaks",
        "style": "dramatic",
        "time_of_day": "golden hour",
        "attraction_type": "destination",
    },
    "city": {
        "keywords": ["ville", "city", "arrivée", "arrival", "transfert", "quartier", "district", "centre-ville", "downtown"],
        "scene_type": "vibrant urban cityscape, mix of modern and traditional architecture",
        "style": "documentary",
        "time_of_day": "blue hour",
        "attraction_type": "destination",
    },
    "market": {
        "keywords": ["marché", "market", "bazar", "bazaar", "shopping", "artisanat", "craft"],
        "scene_type": "colorful bustling local market, authentic culture, vibrant street life",
        "style": "vibrant",
        "time_of_day": "morning light",
        "attraction_type": "attraction",
    },
    "nature": {
        "keywords": ["jungle", "forêt", "forest", "parc national", "national park", "cascade", "waterfall", "rivière", "river", "lac", "lake", "mangrove"],
        "scene_type": "lush tropical nature, dense vegetation, pristine wilderness",
        "style": "cinematic",
        "time_of_day": "soft diffused light",
        "attraction_type": "activity",
    },
    "rice_fields": {
        "keywords": ["rizière", "rice field", "rice terrace", "paddy", "riz"],
        "scene_type": "terraced rice fields, emerald green paddy landscape, pastoral beauty",
        "style": "aerial view",
        "time_of_day": "golden hour",
        "attraction_type": "destination",
    },
    "palace": {
        "keywords": ["palais", "palace", "citadelle", "citadel", "château", "castle", "fort", "fortress", "royal"],
        "scene_type": "grand royal palace, ornate architecture, majestic monument",
        "style": "cinematic",
        "time_of_day": "golden hour",
        "attraction_type": "attraction",
    },
    "village": {
        "keywords": ["village", "communauté", "community", "ethnie", "ethnic", "tribu", "tribe", "local", "authentique"],
        "scene_type": "charming traditional village, authentic local life, cultural heritage",
        "style": "documentary",
        "time_of_day": "morning light",
        "attraction_type": "activity",
    },
    "cruise": {
        "keywords": ["croisière", "cruise", "bateau", "boat", "jonque", "junk", "kayak", "pirogue", "canoe"],
        "scene_type": "scenic waterway cruise, traditional boat on calm water, riverside landscape",
        "style": "cinematic",
        "time_of_day": "golden hour",
        "attraction_type": "activity",
    },
    "food": {
        "keywords": ["cuisine", "cooking", "gastronomie", "gastronomy", "cours de cuisine", "cooking class", "street food", "dégustation"],
        "scene_type": "authentic local cuisine preparation, colorful fresh ingredients, culinary culture",
        "style": "vibrant",
        "time_of_day": "warm indoor light",
        "attraction_type": "activity",
    },
}

# Default scene when no keywords match
DEFAULT_SCENE = {
    "scene_type": "beautiful scenic travel landscape, inspiring destination",
    "style": "photorealistic",
    "time_of_day": "golden hour",
    "attraction_type": "destination",
}


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class DayImageSpec:
    """Specification for an image to generate for a trip day."""
    day_number: int
    trip_day_id: int
    location: str
    scene_type: str
    style: str
    time_of_day: str
    attraction_type: str
    attraction_slug: str
    seo_filename: str
    prompt: str
    negative_prompt: str
    alt_text: str


@dataclass
class GenerationResult:
    """Result of generating images for a circuit."""
    trip_id: int
    generated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    images: List[Dict] = field(default_factory=list)


# ============================================================================
# Slug / SEO utilities
# ============================================================================

def slugify(text: str, max_length: int = 60) -> str:
    """
    Convert text to SEO-friendly slug.
    Removes accents, lowercases, replaces spaces with hyphens.
    """
    # Normalize unicode (remove accents)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Lowercase
    text = text.lower()

    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)

    # Remove leading/trailing hyphens and collapse multiples
    text = re.sub(r"-+", "-", text).strip("-")

    # Truncate to max length (don't cut mid-word)
    if len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]

    return text or "image"


def build_seo_filename(
    location: str,
    scene_type: str,
    destination: str,
    day_number: int,
) -> str:
    """
    Build an SEO-friendly filename from components.

    Examples:
    - temple-wat-pho-bouddha-couche-bangkok
    - plage-railay-krabi-falaises-calcaire
    - riziere-terrasses-sapa-vietnam-paysage
    """
    # Combine key parts
    parts = []

    # Add scene-related keyword first (most important for SEO)
    scene_keyword = scene_type.split(",")[0].strip() if scene_type else ""
    if scene_keyword:
        parts.append(scene_keyword)

    # Add location
    if location:
        parts.append(location)

    # Add destination
    if destination:
        parts.append(destination)

    combined = " ".join(parts)
    slug = slugify(combined)

    # Always include day number to ensure uniqueness per day
    # (same destination on different days must produce different files)
    slug = f"{slug}-jour-{day_number}"

    return slug


def extract_location_name(day: TripDay) -> str:
    """Extract the main location name from a trip day."""
    # Prefer location_to (destination of the day) over location_from
    location = day.location_to or day.location_from or ""

    # Also try to get from title
    if not location and day.title:
        # Extract location from title like "Bangkok - Temples" or "Visite de Chiang Mai"
        location = day.title

    return location.strip()


def extract_landmarks(day_title: Optional[str], day_description: Optional[str]) -> List[str]:
    """
    Extract specific landmark/site names from day title and description.

    Looks for proper nouns (capitalized words), known landmark patterns,
    and specific place names to anchor the image to REAL locations.
    """
    landmarks = []
    text = f"{day_title or ''} {day_description or ''}"

    if not text.strip():
        return landmarks

    # Patterns for real place names (proper nouns, often capitalized)
    # Match sequences of 2+ capitalized words (e.g., "Wat Pho", "Grand Palace", "Baie d'Ha Long")
    proper_noun_pattern = re.compile(
        r'\b([A-Z][a-zéèêëàâäùûüôöîïçñ]+(?:\s+(?:de|du|des|d\'|el|al|the|di|del|van|von|da)?\s*)?'
        r'[A-Z][a-zéèêëàâäùûüôöîïçñ]+(?:\s+[A-Z][a-zéèêëàâäùûüôöîïçñ]+)*)\b'
    )

    # Known landmark prefixes (temple names, natural sites, etc.)
    landmark_prefixes = [
        "wat ", "temple ", "pagode ", "palais ", "palace ", "parc national ",
        "national park ", "mount ", "mont ", "île ", "island ", "lac ", "lake ",
        "baie ", "bay ", "cascade ", "chute ", "falls ", "musée ", "museum ",
        "marché ", "market ", "pont ", "bridge ", "fort ", "citadelle ",
        "cathédrale ", "cathedral ", "mosquée ", "mosque ", "grotte ", "cave ",
    ]

    text_lower = text.lower()

    # Extract landmarks by prefix matching
    # Process title and description separately to avoid cross-boundary captures
    text_segments = [s.strip() for s in [day_title or "", day_description or ""] if s.strip()]

    for segment in text_segments:
        segment_lower = segment.lower()
        for prefix in landmark_prefixes:
            idx = 0
            while True:
                pos = segment_lower.find(prefix, idx)
                if pos == -1:
                    break
                start = pos
                end = start + len(prefix)
                # Capture the landmark name — stop at punctuation or linking words
                rest = segment[end:end + 50]
                # Stop at punctuation, conjunctions, prepositions indicating new clause
                match_end = re.search(
                    r'[,.\n;:()\[\]!?]| et | avec | puis | pour | dans | sur | vers | après | avant | ou ',
                    rest
                )
                if match_end:
                    name_part = rest[:match_end.start()].strip()
                else:
                    name_part = rest.strip()

                if name_part:
                    full_landmark = segment[start:end] + name_part
                    full_landmark = full_landmark.strip().rstrip('.')
                    # Only keep reasonable landmark names (4-60 chars)
                    if 4 < len(full_landmark) < 60:
                        landmarks.append(full_landmark)
                idx = end

    # Extract proper noun sequences from original text
    for match in proper_noun_pattern.finditer(text):
        name = match.group(0).strip()
        # Filter out common French words that happen to start sentences
        skip_words = {
            "Arrivée", "Départ", "Visite", "Journée", "Matinée", "Après",
            "Transfert", "Installation", "Découverte", "Excursion", "Retour",
            "Option", "Balade", "Continuation", "Route", "Nuit", "Petit",
            "Déjeuner", "Dîner", "Temps", "Jour", "Libre", "Vol",
        }
        first_word = name.split()[0] if name else ""
        if first_word not in skip_words and len(name) > 3:
            landmarks.append(name)

    # Deduplicate: remove entries that are substrings of other entries
    # and filter noise (entries containing common verbs/descriptions)
    noise_words = [
        "journée", "visite", "excursion", "trek", "balade", "transfert",
        "nuit", "départ", "arrivée", "retour", "continuation",
        "célèbre", "rendu", "film",
    ]

    cleaned = []
    for lm in landmarks:
        lm_lower = lm.lower()
        # Skip if it contains noise words (descriptions, not names)
        has_noise = any(nw in lm_lower for nw in noise_words)
        if has_noise:
            continue
        cleaned.append(lm)

    # Remove entries that contain already-seen landmarks as substrings
    # e.g., if "Wat Phra Kaew" is found, skip "Palace et Wat Phra Kaew"
    unique = []
    seen_lower = set()
    for lm in sorted(cleaned, key=len):  # Process shortest first
        lm_lower = lm.lower()
        already_seen = lm_lower in seen_lower
        if already_seen:
            continue
        # Check if any existing landmark is a substring of this one
        # If so, this entry is redundant (e.g., "Palace et Wat Phra Kaew" when "Wat Phra Kaew" exists)
        is_superset = any(existing in lm_lower for existing in seen_lower if len(existing) > 3)
        if not is_superset:
            seen_lower.add(lm_lower)
            unique.append(lm)

    return unique[:5]  # Max 5 landmarks


# ============================================================================
# Scene analysis
# ============================================================================

def analyze_day_content(day: TripDay) -> Dict:
    """
    Analyze a trip day's description and title to determine the scene type.
    Returns scene properties for prompt generation.
    """
    text = f"{day.title or ''} {day.description or ''}".lower()

    # Score each scene type by keyword matches
    best_scene = None
    best_score = 0

    for scene_name, scene_info in SCENE_KEYWORDS.items():
        score = sum(1 for kw in scene_info["keywords"] if kw in text)
        if score > best_score:
            best_score = score
            best_scene = scene_info

    if best_scene is None or best_score == 0:
        return DEFAULT_SCENE.copy()

    return {
        "scene_type": best_scene["scene_type"],
        "style": best_scene["style"],
        "time_of_day": best_scene["time_of_day"],
        "attraction_type": best_scene["attraction_type"],
    }


# ============================================================================
# Prompt generation
# ============================================================================

def build_prompt(
    location: str,
    destination_name: str,
    scene_type: str,
    style: str,
    time_of_day: str,
    day_title: Optional[str] = None,
    day_description: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Build an optimized prompt and negative prompt for Vertex AI.

    Focuses on generating images of REAL, recognizable locations rather than
    generic or fictional scenes. Extracts specific landmark names from the
    day description and injects them into the prompt.

    Returns:
        Tuple of (prompt, negative_prompt)
    """
    # Style descriptions
    style_map = {
        "cinematic": "cinematic lighting, movie scene quality, dramatic atmosphere",
        "photorealistic": "ultra realistic, high resolution, professional DSLR photo quality",
        "dramatic": "dramatic lighting, epic scale, awe-inspiring composition",
        "documentary": "authentic documentary style, natural lighting, candid atmosphere",
        "vibrant": "vibrant saturated colors, energetic composition, lively atmosphere",
        "aerial view": "aerial drone perspective, bird's eye view, sweeping landscape",
    }

    style_desc = style_map.get(style, "professional photography, high quality")

    # Extract specific landmarks from the day description
    landmarks = extract_landmarks(day_title, day_description)

    # Build the location part — prioritize real landmark names
    if landmarks:
        # Use the most specific landmark as the main subject
        main_landmark = landmarks[0]
        other_landmarks = ", ".join(landmarks[1:3]) if len(landmarks) > 1 else ""

        location_desc = f"{main_landmark}, {location}, {destination_name}"
        if other_landmarks:
            location_desc += f", near {other_landmarks}"
    else:
        location_desc = f"{location}, {destination_name}"

    prompt = f"""Photorealistic image of the real existing place {location_desc},
exactly as it looks in reality, famous landmark photography,
{time_of_day} lighting, {style_desc},
accurate representation of the actual location,
travel magazine quality, National Geographic style,
stunning composition, high dynamic range,
professional travel photography, no watermarks, no people"""

    # Add scene context from description (more chars for better specificity)
    if day_description and len(day_description) > 20:
        # Use up to 400 chars of description for more context
        context = day_description[:400].strip()
        prompt += f",\nscene details: {context}"

    negative_prompt = """blurry, low quality, distorted, ugly,
watermark, text, logo, signature, overlay,
oversaturated, overexposed, underexposed,
fictional place, imaginary location, fantasy architecture,
AI artifacts, unrealistic colors, impossible geometry,
tourists crowds, modern vehicles in foreground,
stock photo watermark, frame, border,
invented buildings, non-existing landmarks"""

    return prompt.strip(), negative_prompt.strip()


# ============================================================================
# Storage upload (SEO nomenclature)
# ============================================================================

async def upload_seo_image(
    image_data: bytes,
    tenant_id: str,
    destination: str,
    attraction_type: str,
    attraction_slug: str,
    seo_filename: str,
    variant_suffix: str,
    file_format: str,
    content_type: str,
) -> Tuple[str, str]:
    """
    Upload an image to Supabase Storage with SEO nomenclature.

    Path: media/{tenant_id}/{destination}/{attraction_type}/{attraction_slug}/{seo_filename}-{variant}.{format}

    Returns:
        Tuple of (storage_path, public_url)
    """
    client = get_supabase_client()

    # Build SEO path
    storage_path = (
        f"media/{tenant_id}/{destination}/{attraction_type}/"
        f"{attraction_slug}/{seo_filename}{variant_suffix}.{file_format}"
    )

    # Upload with retry logic for timeout issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=image_data,
                file_options={
                    "content-type": content_type,
                    "cache-control": "31536000",  # 1 year (immutable variants)
                },
            )
            break  # Success
        except Exception as e:
            error_str = str(e)
            if "Duplicate" in error_str or "already exists" in error_str:
                # File exists, try to update it
                try:
                    client.storage.from_(BUCKET_NAME).update(
                        path=storage_path,
                        file=image_data,
                        file_options={
                            "content-type": content_type,
                            "cache-control": "31536000",
                        },
                    )
                    break  # Success
                except Exception as update_err:
                    if attempt < max_retries - 1:
                        import time
                        logger.warning(f"Upload update retry {attempt + 1}/{max_retries} for {storage_path}: {update_err}")
                        time.sleep(2 * (attempt + 1))  # Exponential backoff
                        client = get_supabase_client()  # Fresh client
                        continue
                    raise
            elif "timeout" in error_str.lower() or "ReadTimeout" in error_str:
                if attempt < max_retries - 1:
                    import time
                    logger.warning(f"Upload timeout retry {attempt + 1}/{max_retries} for {storage_path}")
                    time.sleep(2 * (attempt + 1))
                    client = get_supabase_client()  # Fresh client
                    continue
                raise
            else:
                raise

    public_url = client.storage.from_(BUCKET_NAME).get_public_url(storage_path)
    return storage_path, public_url


# ============================================================================
# Main orchestrator
# ============================================================================

def prepare_day_specs(
    trip: Trip,
    destination_name: str,
    days: Optional[List] = None,
    days_filter: Optional[List[int]] = None,
) -> List[DayImageSpec]:
    """
    Analyze all days of a trip and prepare image specifications.

    Args:
        trip: The trip object
        destination_name: Slugified destination name
        days: Pre-loaded list of TripDay objects (avoids lazy loading in async)
        days_filter: Optional list of day numbers to process (None = all)

    Returns:
        List of DayImageSpec ready for generation
    """
    specs = []

    trip_days = days if days is not None else trip.days
    for day in trip_days:
        # Skip days not in filter
        if days_filter and day.day_number not in days_filter:
            continue

        # Skip days without content
        if not day.title and not day.description:
            continue

        # Analyze content
        scene = analyze_day_content(day)
        location = extract_location_name(day)

        if not location:
            location = destination_name.replace("-", " ").title()

        # Build slug for the attraction
        attraction_slug = slugify(location, max_length=40)

        # Build SEO filename
        seo_filename = build_seo_filename(
            location=location,
            scene_type=scene["scene_type"],
            destination=destination_name,
            day_number=day.day_number,
        )

        # Build prompt
        prompt, negative_prompt = build_prompt(
            location=location,
            destination_name=destination_name.replace("-", " ").title(),
            scene_type=scene["scene_type"],
            style=scene["style"],
            time_of_day=scene["time_of_day"],
            day_title=day.title,
            day_description=day.description,
        )

        # Build alt text
        alt_text = f"{day.title or location} - {destination_name.replace('-', ' ').title()}"

        specs.append(DayImageSpec(
            day_number=day.day_number,
            trip_day_id=day.id,
            location=location,
            scene_type=scene["scene_type"],
            style=scene["style"],
            time_of_day=scene["time_of_day"],
            attraction_type=scene["attraction_type"],
            attraction_slug=attraction_slug,
            seo_filename=seo_filename,
            prompt=prompt,
            negative_prompt=negative_prompt,
            alt_text=alt_text,
        ))

    return specs


async def generate_and_process_image(
    spec: DayImageSpec,
    image_service: ImageGenerationService,
    tenant_id: str,
    destination: str,
    quality: str = "high",
) -> Optional[Dict]:
    """
    Generate a single image, process it, and upload all variants.

    Returns:
        Dict with all URLs and metadata, or None on failure
    """
    try:
        # Choose model based on quality
        model_name = image_service.model_name

        # Generate image via Vertex AI
        logger.info(f"Generating image for day {spec.day_number}: {spec.location}")
        images = await image_service.generate_image(
            prompt=spec.prompt,
            negative_prompt=spec.negative_prompt,
            number_of_images=1,
            aspect_ratio="16:9",
            guidance_scale=8.0,
        )

        if not images:
            logger.warning(f"No image generated for day {spec.day_number}")
            return None

        # Get raw image bytes (PNG from Vertex AI)
        raw_bytes = image_service.get_image_bytes(images[0])

        # Process image → generate all variants
        processing_result = process_image(raw_bytes)

        # Upload all variants with SEO nomenclature
        urls = {}
        srcset_entries = []

        for variant in processing_result.variants:
            # Map size names to our naming
            variant_suffix = f"-{variant.size_name}"
            file_format = variant.format

            storage_path, public_url = await upload_seo_image(
                image_data=variant.data,
                tenant_id=str(tenant_id),
                destination=destination,
                attraction_type=spec.attraction_type,
                attraction_slug=spec.attraction_slug,
                seo_filename=spec.seo_filename,
                variant_suffix=variant_suffix,
                file_format=file_format,
                content_type=variant.content_type,
            )

            # Organize URLs by role
            key = f"{variant.format}_{variant.size_name}"
            urls[key] = public_url

            srcset_entries.append({
                "url": public_url,
                "width": variant.width,
                "height": variant.height,
                "format": variant.format,
                "size": variant.size_name,
                "file_size": variant.file_size,
            })

        # Also upload the original as the master AVIF
        from app.services.image_processor import save_as_avif, save_as_webp
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(raw_bytes))
        master_avif = save_as_avif(img)
        master_path, master_url = await upload_seo_image(
            image_data=master_avif,
            tenant_id=str(tenant_id),
            destination=destination,
            attraction_type=spec.attraction_type,
            attraction_slug=spec.attraction_slug,
            seo_filename=spec.seo_filename,
            variant_suffix="",
            file_format="avif",
            content_type="image/avif",
        )

        return {
            "day_number": spec.day_number,
            "trip_day_id": spec.trip_day_id,
            "location": spec.location,
            "seo_filename": spec.seo_filename,
            "destination": destination,
            "attraction_type": spec.attraction_type,
            "attraction_slug": spec.attraction_slug,
            "storage_path": master_path,
            "url": master_url,
            "url_avif": urls.get("avif_medium") or urls.get("avif_large") or master_url,
            "url_webp": urls.get("webp_medium") or urls.get("webp_large"),
            "url_medium": urls.get("avif_medium") or urls.get("webp_medium"),
            "url_large": urls.get("avif_large") or urls.get("webp_large"),
            "url_hero": urls.get("avif_large") or master_url,
            "thumbnail_url": urls.get("webp_thumbnail") or urls.get("avif_thumbnail"),
            "lqip_data_url": processing_result.lqip_data_url,
            "srcset_json": srcset_entries,
            "width": processing_result.original_width,
            "height": processing_result.original_height,
            "prompt": spec.prompt,
            "negative_prompt": spec.negative_prompt,
            "alt_text": spec.alt_text,
            "ai_model": image_service.model_name,
        }

    except Exception as e:
        logger.exception(f"Error generating image for day {spec.day_number}: {e}")
        return None


async def generate_circuit_images(
    db: AsyncSession,
    trip_id: int,
    tenant_id: str,
    days: Optional[List[int]] = None,
    overwrite: bool = False,
    quality: str = "high",
) -> GenerationResult:
    """
    Generate images for all days of a circuit.

    Args:
        db: Database session
        trip_id: ID of the trip/circuit
        tenant_id: Tenant UUID
        days: Optional list of day numbers to process (None = all)
        overwrite: Whether to overwrite existing images
        quality: "high" (Imagen 3) or "fast" (Imagen 3 Fast)

    Returns:
        GenerationResult with summary and image details
    """
    result = GenerationResult(trip_id=trip_id)

    # Load trip
    trip_result = await db.execute(
        select(Trip).where(Trip.id == trip_id)
    )
    trip = trip_result.scalar_one_or_none()

    if not trip:
        result.errors.append(f"Trip {trip_id} not found")
        return result

    # Load days separately (async-safe, avoids lazy loading issues)
    from app.models.trip import TripDay
    days_result = await db.execute(
        select(TripDay).where(TripDay.trip_id == trip_id).order_by(TripDay.day_number)
    )
    trip_days = list(days_result.scalars().all())

    # Determine destination name
    country_code = trip.destination_country or ""
    destination_name = COUNTRY_DESTINATIONS.get(country_code.upper(), "")
    if not destination_name:
        destination_name = slugify(country_code or "unknown")

    logger.info(
        f"Generating images for trip '{trip.name}' (id={trip_id}), "
        f"destination={destination_name}, {len(trip_days)} days"
    )

    # Check for existing photos if not overwriting
    if not overwrite:
        existing_stmt = (
            select(TripPhoto.day_number)
            .where(TripPhoto.trip_id == trip_id)
        )
        existing_result = await db.execute(existing_stmt)
        existing_days = {row[0] for row in existing_result.fetchall()}
    else:
        existing_days = set()

    # Prepare image specifications
    specs = prepare_day_specs(trip, destination_name, days=trip_days, days_filter=days)

    # Filter out already existing
    filtered_specs = []
    for spec in specs:
        if spec.day_number in existing_days:
            result.skipped += 1
            logger.info(f"Skipping day {spec.day_number} (already has image)")
        else:
            filtered_specs.append(spec)

    if not filtered_specs:
        logger.info("No images to generate")
        return result

    # Initialize Vertex AI service
    model_name = (
        ImageGenerationService.MODEL_IMAGEN_3_FAST
        if quality == "fast"
        else ImageGenerationService.MODEL_IMAGEN_3
    )
    image_service = ImageGenerationService(model_name=model_name)

    # Generate images for each day
    for spec in filtered_specs:
        image_data = await generate_and_process_image(
            spec=spec,
            image_service=image_service,
            tenant_id=tenant_id,
            destination=destination_name,
            quality=quality,
        )

        if image_data is None:
            result.errors.append(f"Failed to generate image for day {spec.day_number}")
            continue

        # Create TripPhoto record in DB
        photo = TripPhoto(
            tenant_id=tenant_id,
            trip_id=trip_id,
            trip_day_id=image_data["trip_day_id"],
            day_number=image_data["day_number"],
            destination=image_data["destination"],
            attraction_type=image_data["attraction_type"],
            attraction_slug=image_data["attraction_slug"],
            seo_filename=image_data["seo_filename"],
            storage_path=image_data["storage_path"],
            url=image_data["url"],
            thumbnail_url=image_data["thumbnail_url"],
            url_avif=image_data["url_avif"],
            url_webp=image_data["url_webp"],
            url_medium=image_data["url_medium"],
            url_large=image_data["url_large"],
            url_hero=image_data["url_hero"],
            srcset_json=image_data["srcset_json"],
            lqip_data_url=image_data["lqip_data_url"],
            width=image_data["width"],
            height=image_data["height"],
            ai_prompt=image_data["prompt"],
            ai_negative_prompt=image_data["negative_prompt"],
            ai_model=image_data["ai_model"],
            ai_generated_at=datetime.now(timezone.utc),
            alt_text=image_data["alt_text"],
            is_hero=(spec.day_number == 1),  # First day = hero image
            is_ai_generated=True,
            is_processed=True,
            sort_order=spec.day_number,
        )

        db.add(photo)
        result.generated += 1

        result.images.append({
            "day": image_data["day_number"],
            "location": image_data["location"],
            "filename": f"{image_data['seo_filename']}.avif",
            "url": image_data["url"],
            "variants": {
                "hero": image_data["url_hero"],
                "large": image_data["url_large"],
                "medium": image_data["url_medium"],
                "thumb": image_data["thumbnail_url"],
                "lqip": image_data["lqip_data_url"],
            },
        })

    # Commit all photos
    await db.commit()

    logger.info(
        f"Generation complete: {result.generated} generated, "
        f"{result.skipped} skipped, {len(result.errors)} errors"
    )

    return result
