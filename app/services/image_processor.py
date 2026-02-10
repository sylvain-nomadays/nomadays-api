"""
Image processing service for optimizing photos.

Generates optimized variants in AVIF and WebP formats with multiple sizes.
Also creates LQIP (Low Quality Image Placeholder) for blur-up effect.
"""

import io
import base64
from typing import Tuple, Dict, Optional, List
from dataclasses import dataclass

from PIL import Image

# AVIF support: Pillow >= 10.1 has native AVIF support.
# Fall back to pillow_avif plugin for older versions.
_avif_supported = False
try:
    import io as _io
    _test_img = Image.new('RGB', (10, 10), 'red')
    _buf = _io.BytesIO()
    _test_img.save(_buf, format='AVIF', quality=50)
    _avif_supported = True
except Exception:
    try:
        import pillow_avif  # noqa: F401
        _avif_supported = True
    except ImportError:
        _avif_supported = False


# ============================================================================
# Configuration
# ============================================================================

# Target sizes for responsive images (width in pixels)
SIZES = {
    "thumbnail": 150,   # Vignettes (30-50 Ko max)
    "small": 400,       # Mobile
    "medium": 800,      # Tablettes / articles (150-200 Ko max)
    "large": 1200,      # Desktop
    "hero": 1920,       # Bannières plein écran (300-500 Ko max)
}

# Quality settings (0-100)
QUALITY = {
    "avif": 65,         # AVIF is very efficient, lower quality still looks great
    "webp": 75,         # WebP needs slightly higher quality
    "jpeg": 80,         # JPEG fallback
}

# Maximum file sizes (bytes) - targets from spec
MAX_SIZES = {
    "hero": 500 * 1024,      # 500KB for hero/banners
    "article": 200 * 1024,   # 200KB for articles
    "thumbnail": 50 * 1024,  # 50KB for thumbnails
}

# LQIP settings
LQIP_SIZE = 20  # Width for blur placeholder (tiny)
LQIP_QUALITY = 30  # Low quality for small file size


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ProcessedVariant:
    """Represents a processed image variant."""
    format: str           # 'avif', 'webp', 'jpeg'
    size_name: str        # 'thumbnail', 'small', 'medium', 'large'
    width: int
    height: int
    data: bytes
    file_size: int
    content_type: str


@dataclass
class ProcessingResult:
    """Result of processing an image."""
    original_width: int
    original_height: int
    variants: List[ProcessedVariant]
    lqip_data_url: str    # Base64 data URL for blur placeholder
    srcset_json: str      # JSON with all srcset URLs (to be filled after upload)


# ============================================================================
# Image Processing Functions
# ============================================================================

def get_dimensions_for_width(original_width: int, original_height: int, target_width: int) -> Tuple[int, int]:
    """Calculate new dimensions maintaining aspect ratio."""
    if target_width >= original_width:
        return original_width, original_height

    ratio = target_width / original_width
    new_height = int(original_height * ratio)
    return target_width, new_height


def resize_image(img: Image.Image, target_width: int) -> Image.Image:
    """Resize image to target width maintaining aspect ratio."""
    original_width, original_height = img.size
    new_width, new_height = get_dimensions_for_width(original_width, original_height, target_width)

    if new_width == original_width:
        return img.copy()

    # Use high-quality downsampling
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def convert_to_rgb(img: Image.Image) -> Image.Image:
    """Convert image to RGB mode if necessary (required for JPEG/WebP)."""
    if img.mode in ('RGBA', 'P'):
        # Create white background for transparent images
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        return background
    elif img.mode != 'RGB':
        return img.convert('RGB')
    return img


def save_as_avif(img: Image.Image, quality: int = QUALITY["avif"]) -> bytes:
    """Save image as AVIF format."""
    if not _avif_supported:
        raise ImportError("AVIF is not supported (need Pillow >= 10.1 or pillow-avif-plugin)")

    img_rgb = convert_to_rgb(img)
    buffer = io.BytesIO()
    img_rgb.save(buffer, format='AVIF', quality=quality)
    return buffer.getvalue()


def save_as_webp(img: Image.Image, quality: int = QUALITY["webp"]) -> bytes:
    """Save image as WebP format."""
    img_rgb = convert_to_rgb(img)
    buffer = io.BytesIO()
    img_rgb.save(buffer, format='WEBP', quality=quality)
    return buffer.getvalue()


def save_as_jpeg(img: Image.Image, quality: int = QUALITY["jpeg"]) -> bytes:
    """Save image as JPEG format."""
    img_rgb = convert_to_rgb(img)
    buffer = io.BytesIO()
    img_rgb.save(buffer, format='JPEG', quality=quality, optimize=True)
    return buffer.getvalue()


def generate_lqip(img: Image.Image) -> str:
    """Generate Low Quality Image Placeholder as base64 data URL."""
    # Resize to tiny size
    width, height = get_dimensions_for_width(img.size[0], img.size[1], LQIP_SIZE)
    tiny = img.resize((width, height), Image.Resampling.LANCZOS)

    # Convert to RGB and save as low-quality JPEG
    tiny_rgb = convert_to_rgb(tiny)
    buffer = io.BytesIO()
    tiny_rgb.save(buffer, format='JPEG', quality=LQIP_QUALITY, optimize=True)

    # Encode as base64 data URL
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"


def optimize_for_size_target(
    img: Image.Image,
    target_width: int,
    max_size: int,
    format: str = "avif"
) -> Tuple[bytes, int]:
    """
    Optimize image for a target file size.
    Reduces quality iteratively until target is met.
    """
    resized = resize_image(img, target_width)

    # Start with default quality
    quality = QUALITY.get(format, 75)
    min_quality = 30

    while quality >= min_quality:
        if format == "avif":
            data = save_as_avif(resized, quality)
        elif format == "webp":
            data = save_as_webp(resized, quality)
        else:
            data = save_as_jpeg(resized, quality)

        if len(data) <= max_size:
            return data, quality

        quality -= 5

    # If we can't meet the target, return best effort
    return data, quality


# ============================================================================
# Main Processing Function
# ============================================================================

def process_image(image_data: bytes) -> ProcessingResult:
    """
    Process an image and generate all optimized variants.

    Returns:
        ProcessingResult containing all variants and LQIP
    """
    # Load image
    img = Image.open(io.BytesIO(image_data))
    original_width, original_height = img.size

    variants: List[ProcessedVariant] = []

    # Generate variants for each size
    for size_name, target_width in SIZES.items():
        # If target is larger than original, use original size (no upscaling)
        effective_width = min(target_width, original_width)
        resized = resize_image(img, effective_width)
        new_width, new_height = resized.size

        # Generate AVIF variant (primary — best compression)
        if _avif_supported:
            try:
                avif_data = save_as_avif(resized)
                variants.append(ProcessedVariant(
                    format="avif",
                    size_name=size_name,
                    width=new_width,
                    height=new_height,
                    data=avif_data,
                    file_size=len(avif_data),
                    content_type="image/avif",
                ))
            except Exception:
                pass

        # Generate WebP variant (fallback)
        webp_data = save_as_webp(resized)
        variants.append(ProcessedVariant(
            format="webp",
            size_name=size_name,
            width=new_width,
            height=new_height,
            data=webp_data,
            file_size=len(webp_data),
            content_type="image/webp",
        ))

    # Generate LQIP
    lqip_data_url = generate_lqip(img)

    return ProcessingResult(
        original_width=original_width,
        original_height=original_height,
        variants=variants,
        lqip_data_url=lqip_data_url,
        srcset_json="",  # Will be filled after upload
    )


def process_image_minimal(image_data: bytes) -> Tuple[bytes, bytes, str, int, int]:
    """
    Simplified processing for immediate use.

    Returns:
        Tuple of (thumbnail_data, medium_data, lqip_data_url, width, height)
    """
    img = Image.open(io.BytesIO(image_data))
    width, height = img.size

    # Generate thumbnail (150px)
    thumbnail = resize_image(img, SIZES["thumbnail"])
    thumbnail_data = save_as_jpeg(thumbnail, 75)

    # Generate medium (800px) - for quick preview
    medium = resize_image(img, SIZES["medium"])
    medium_data = save_as_webp(medium)

    # Generate LQIP
    lqip_data_url = generate_lqip(img)

    return thumbnail_data, medium_data, lqip_data_url, width, height


def get_image_dimensions(image_data: bytes) -> Tuple[int, int]:
    """Get dimensions of an image without full processing."""
    img = Image.open(io.BytesIO(image_data))
    return img.size
