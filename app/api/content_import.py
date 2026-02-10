"""
Content Import API - Import and analyze content from existing websites

This API allows importing content from existing websites:
1. Fetch the webpage content
2. Extract content AS-IS (preserving original text)
3. Extract slug from URL to maintain identical URLs
4. Analyze quality and provide improvement suggestions
5. Create a ContentEntity with translations
"""

import json
import re
from datetime import datetime
from typing import List, Optional, Literal
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, TenantId
from app.models.content import ContentEntity, ContentTranslation, ContentEntityType, ContentStatus
from app.config import get_settings

router = APIRouter(prefix="/content/import", tags=["Content Import"])

settings = get_settings()

# Entity type options
EntityType = Literal["attraction", "destination", "activity", "accommodation", "eating", "region"]

# Language options
LanguageCode = Literal["fr", "en", "it", "es", "de"]


# ============================================================================
# Schemas
# ============================================================================

class ContentImportRequest(BaseModel):
    """Request to import content from URL."""
    url: HttpUrl
    entity_type: EntityType
    language: LanguageCode = "fr"


class QualityAlert(BaseModel):
    """A quality issue found in the content."""
    type: Literal["seo", "structure", "content", "outdated", "spelling"]
    severity: Literal["error", "warning", "info"]
    message: str
    suggestion: Optional[str] = None
    location: Optional[str] = None  # e.g., "meta_title", "content", "paragraph 3"


class ExtractedContent(BaseModel):
    """Content extracted from webpage - AS-IS."""
    title: str
    slug: str  # Extracted from URL path
    original_url: str
    excerpt: Optional[str] = None
    content_markdown: Optional[str] = None
    content_html: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    # Location info
    location_name: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    # Additional data
    rating: Optional[float] = None
    images: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class ContentAnalysis(BaseModel):
    """Quality analysis of the content."""
    overall_score: int  # 0-100
    alerts: List[QualityAlert]
    word_count: int
    reading_time_minutes: int
    has_meta_title: bool
    has_meta_description: bool
    meta_title_length: int
    meta_description_length: int
    heading_count: int
    image_count: int
    internal_links_count: int


class ContentImportPreview(BaseModel):
    """Preview of content before import - NO analysis at import time."""
    source_url: str
    entity_type: str
    language: str
    extracted: ExtractedContent
    raw_text_length: int


class ContentImportConfirmRequest(BaseModel):
    """Confirm and create the content entity."""
    source_url: str
    entity_type: EntityType
    language: LanguageCode
    # Editable fields
    title: str
    slug: str
    excerpt: Optional[str] = None
    content_markdown: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    # Location
    location_name: Optional[str] = None
    country_code: Optional[str] = None
    # Optional
    cover_image_url: Optional[str] = None
    rating: Optional[float] = None
    tags: Optional[List[str]] = None


class ContentImportResponse(BaseModel):
    """Response after creating content."""
    id: str
    entity_type: str
    status: str
    translations_created: List[str]


# ============================================================================
# Content Extraction (AS-IS, no rewriting)
# ============================================================================

def extract_slug_from_url(url: str) -> str:
    """
    Extract only the final segment of URL path as slug.

    Example: guide-thailande/destination/chiang-mai → chiang-mai
    """
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    parts = [p for p in path.split('/') if p]

    if not parts:
        return 'import'

    # Get the last non-empty segment
    slug = parts[-1]

    # Remove file extensions (.html, .php, .htm, .asp, .aspx)
    slug = re.sub(r'\.(html|php|htm|asp|aspx)$', '', slug, flags=re.IGNORECASE)

    return slug if slug else 'import'


def html_to_markdown(html_content: str) -> str:
    """
    Convert HTML content to Markdown using markdownify library.

    This properly handles nested elements, links, images, lists, etc.
    """
    # Use markdownify for robust conversion
    markdown = md(
        html_content,
        heading_style="ATX",         # Use # style headings
        bullets="-",                  # Use - for bullet points
        strip=['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript'],
        convert=['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'img', 'strong', 'em', 'b', 'i',
                 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'br', 'hr'],
    )

    # Clean up excessive whitespace
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    markdown = re.sub(r' +', ' ', markdown)

    return markdown.strip()


def extract_content_from_html(html_content: str, url: str) -> ExtractedContent:
    """Extract content from HTML AS-IS (no AI rewriting)."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract slug from URL
    slug = extract_slug_from_url(url)

    # Get page title
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else ""

    # Try to find H1 as main title
    h1 = soup.find('h1')
    main_title = h1.get_text(strip=True) if h1 else page_title

    # Clean title (remove site name suffix like "| Voyage Thailande")
    main_title = re.split(r'\s*[\|–-]\s*', main_title)[0].strip()

    # Get meta description
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
    meta_description = meta_desc_tag.get('content', '') if meta_desc_tag else ""

    # Get meta title (og:title or title)
    og_title = soup.find('meta', attrs={'property': 'og:title'})
    meta_title = og_title.get('content', '') if og_title else page_title
    meta_title = re.split(r'\s*[\|–-]\s*', meta_title)[0].strip()

    # Remove scripts, styles, nav, footer for content extraction
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript']):
        tag.decompose()

    # Find main content area
    main_content = (
        soup.find('main') or
        soup.find('article') or
        soup.find('div', class_=re.compile(r'content|article|post|entry', re.I)) or
        soup.find('body')
    )

    # Get HTML content
    content_html = str(main_content) if main_content else ""

    # Convert to markdown
    content_markdown = html_to_markdown(content_html) if main_content else ""

    # Extract excerpt (first paragraph or meta description)
    first_p = soup.find('p')
    excerpt = first_p.get_text(strip=True)[:200] if first_p else meta_description[:200]

    # Extract images
    images = []
    for img in soup.find_all('img', src=True):
        src = img.get('src', '')
        if src and not src.startswith('data:') and 'logo' not in src.lower() and 'icon' not in src.lower():
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                parsed = urlparse(url)
                src = f"{parsed.scheme}://{parsed.netloc}{src}"
            if src not in images:
                images.append(src)
    images = images[:10]  # Limit to 10 images

    return ExtractedContent(
        title=main_title or "Sans titre",
        slug=slug,
        original_url=url,
        excerpt=excerpt if excerpt else None,
        content_markdown=content_markdown if content_markdown else None,
        content_html=content_html if content_html else None,
        meta_title=meta_title[:70] if meta_title else None,
        meta_description=meta_description[:170] if meta_description else None,
        images=images if images else None,
    )


# ============================================================================
# AI Quality Analysis
# ============================================================================

async def call_claude_api(prompt: str, system_prompt: str = "") -> str:
    """Call Claude API for content analysis."""
    import anthropic

    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthropic API key not configured"
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system_prompt if system_prompt else "You are a content quality analyst.",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text


async def analyze_content_quality(extracted: ExtractedContent, language: str) -> ContentAnalysis:
    """Analyze content quality and generate alerts."""

    alerts = []
    content = extracted.content_markdown or ""

    # Basic metrics
    word_count = len(content.split()) if content else 0
    reading_time = max(1, word_count // 200)
    heading_count = content.count('##') + content.count('# ')
    image_count = len(extracted.images) if extracted.images else 0

    # Meta analysis
    meta_title_length = len(extracted.meta_title) if extracted.meta_title else 0
    meta_description_length = len(extracted.meta_description) if extracted.meta_description else 0

    # === SEO Alerts ===

    # Meta title
    if not extracted.meta_title:
        alerts.append(QualityAlert(
            type="seo",
            severity="error",
            message="Meta title manquant",
            suggestion="Ajoutez un meta title de 50-60 caractères incluant le mot-clé principal",
            location="meta_title"
        ))
    elif meta_title_length < 30:
        alerts.append(QualityAlert(
            type="seo",
            severity="warning",
            message=f"Meta title trop court ({meta_title_length} caractères)",
            suggestion="Le meta title devrait faire 50-60 caractères pour un affichage optimal dans Google",
            location="meta_title"
        ))
    elif meta_title_length > 60:
        alerts.append(QualityAlert(
            type="seo",
            severity="warning",
            message=f"Meta title trop long ({meta_title_length} caractères)",
            suggestion="Le meta title sera tronqué dans Google. Raccourcissez-le à 60 caractères max",
            location="meta_title"
        ))

    # Meta description
    if not extracted.meta_description:
        alerts.append(QualityAlert(
            type="seo",
            severity="error",
            message="Meta description manquante",
            suggestion="Ajoutez une meta description de 150-160 caractères avec un appel à l'action",
            location="meta_description"
        ))
    elif meta_description_length < 120:
        alerts.append(QualityAlert(
            type="seo",
            severity="warning",
            message=f"Meta description trop courte ({meta_description_length} caractères)",
            suggestion="Enrichissez la meta description (150-160 caractères) pour améliorer le CTR",
            location="meta_description"
        ))
    elif meta_description_length > 160:
        alerts.append(QualityAlert(
            type="seo",
            severity="info",
            message=f"Meta description légèrement longue ({meta_description_length} caractères)",
            suggestion="La description sera peut-être tronquée. Idéalement 150-160 caractères",
            location="meta_description"
        ))

    # === Structure Alerts ===

    if word_count < 300:
        alerts.append(QualityAlert(
            type="content",
            severity="warning",
            message=f"Contenu court ({word_count} mots)",
            suggestion="Un contenu de 800-1500 mots performe mieux en SEO. Enrichissez avec des détails pratiques",
            location="content"
        ))

    if heading_count < 2 and word_count > 300:
        alerts.append(QualityAlert(
            type="structure",
            severity="warning",
            message="Peu de sous-titres",
            suggestion="Ajoutez des sous-titres (H2, H3) pour améliorer la lisibilité et le SEO",
            location="content"
        ))

    if image_count == 0:
        alerts.append(QualityAlert(
            type="content",
            severity="warning",
            message="Aucune image détectée",
            suggestion="Ajoutez des photos pour illustrer le contenu et améliorer l'engagement",
            location="images"
        ))

    # === AI-powered deep analysis (if content is substantial) ===
    if word_count > 100 and settings.anthropic_api_key:
        try:
            ai_alerts = await analyze_with_ai(extracted, language)
            alerts.extend(ai_alerts)
        except Exception as e:
            # Don't fail if AI analysis fails
            print(f"AI analysis failed: {e}")

    # Calculate overall score
    error_count = sum(1 for a in alerts if a.severity == "error")
    warning_count = sum(1 for a in alerts if a.severity == "warning")

    score = 100
    score -= error_count * 15
    score -= warning_count * 5
    score = max(0, min(100, score))

    return ContentAnalysis(
        overall_score=score,
        alerts=alerts,
        word_count=word_count,
        reading_time_minutes=reading_time,
        has_meta_title=bool(extracted.meta_title),
        has_meta_description=bool(extracted.meta_description),
        meta_title_length=meta_title_length,
        meta_description_length=meta_description_length,
        heading_count=heading_count,
        image_count=image_count,
        internal_links_count=0,  # TODO: count internal links
    )


async def analyze_with_ai(extracted: ExtractedContent, language: str) -> List[QualityAlert]:
    """Use AI to analyze content for deeper issues."""

    content_preview = (extracted.content_markdown or "")[:3000]

    system_prompt = """Tu es un expert en contenu touristique et SEO.
Analyse le contenu fourni et identifie les problèmes de qualité.
Réponds UNIQUEMENT avec un tableau JSON d'alertes."""

    prompt = f"""Analyse ce contenu touristique et identifie les problèmes :

Titre: {extracted.title}
Contenu:
---
{content_preview}
---

Vérifie:
1. Informations potentiellement obsolètes (prix, horaires, "depuis 2020", etc.)
2. Fautes d'orthographe ou de grammaire flagrantes
3. Phrases trop longues ou mal structurées
4. Manque d'informations pratiques (horaires, prix, accès)
5. Ton inapproprié pour du contenu voyage

Réponds avec un JSON array (max 5 alertes les plus importantes):
[
  {{
    "type": "outdated|spelling|content|structure",
    "severity": "error|warning|info",
    "message": "Description courte du problème",
    "suggestion": "Comment corriger",
    "location": "Où dans le contenu (optionnel)"
  }}
]

Si aucun problème majeur, réponds: []"""

    try:
        response = await call_claude_api(prompt, system_prompt)

        # Parse JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            data = json.loads(json_match.group())
            return [QualityAlert(**item) for item in data[:5]]
    except Exception as e:
        print(f"AI analysis parsing failed: {e}")

    return []


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/preview", response_model=ContentImportPreview)
async def preview_content_import(
    request: ContentImportRequest,
    user: CurrentUser,
):
    """
    Preview content extraction from a URL.
    Returns extracted data AS-IS without analysis.
    SEO analysis is done post-import via /content/{id}/analyze-seo endpoint.
    """
    url_str = str(request.url)

    # Fetch webpage
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': f'{request.language},en;q=0.9',
            }
            response = await client.get(url_str, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Impossible de récupérer la page: {str(e)}"
        )

    html_content = response.text

    # Extract content AS-IS (no analysis at import - done post-import)
    extracted = extract_content_from_html(html_content, url_str)

    return ContentImportPreview(
        source_url=url_str,
        entity_type=request.entity_type,
        language=request.language,
        extracted=extracted,
        raw_text_length=len(html_content),
    )


@router.post("/confirm", response_model=ContentImportResponse, status_code=201)
async def confirm_content_import(
    request: ContentImportConfirmRequest,
    db: DbSession,
    user: CurrentUser,
    tenant_id: TenantId,
):
    """
    Confirm and create a content entity from extracted data.
    """
    # Validate entity type
    try:
        ContentEntityType(request.entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type: {request.entity_type}"
        )

    # Create entity
    entity = ContentEntity(
        tenant_id=tenant_id,
        entity_type=request.entity_type,
        status=ContentStatus.DRAFT.value,
        cover_image_url=request.cover_image_url,
        rating=request.rating,
        canonical_url=request.source_url,  # Store original URL as canonical
        created_by=user.id,
        updated_by=user.id,
    )

    db.add(entity)
    await db.flush()

    # Create translation
    translation = ContentTranslation(
        entity_id=entity.id,
        language_code=request.language,
        title=request.title,
        slug=request.slug,
        excerpt=request.excerpt,
        content_markdown=request.content_markdown,
        meta_title=request.meta_title,
        meta_description=request.meta_description,
        is_primary=True,
        word_count=len(request.content_markdown.split()) if request.content_markdown else 0,
        reading_time_minutes=max(1, len(request.content_markdown.split()) // 200) if request.content_markdown else 0,
    )

    db.add(translation)
    await db.commit()

    return ContentImportResponse(
        id=str(entity.id),
        entity_type=entity.entity_type,
        status=entity.status,
        translations_created=[request.language],
    )


@router.post("/batch", response_model=List[ContentImportPreview])
async def batch_preview_import(
    urls: List[HttpUrl],
    entity_type: EntityType,
    language: LanguageCode = "fr",
    user: CurrentUser = None,
):
    """
    Preview multiple URLs for batch import.
    Limited to 10 URLs at a time.
    """
    if len(urls) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 URLs par batch"
        )

    previews = []
    for url in urls:
        try:
            request = ContentImportRequest(
                url=url,
                entity_type=entity_type,
                language=language,
            )
            preview = await preview_content_import(request, user)
            previews.append(preview)
        except HTTPException:
            # Skip failed URLs
            continue

    return previews
