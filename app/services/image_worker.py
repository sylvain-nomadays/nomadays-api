"""
Background worker for processing images.

Processes unprocessed photos and generates optimized variants.
Can be run as a background task or scheduled job.
"""

import asyncio
import json
import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccommodationPhoto
from app.services.image_processor import (
    process_image,
    ProcessedVariant,
    SIZES,
)
from app.services.storage import (
    get_supabase_client,
    BUCKET_NAME,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Worker Functions
# ============================================================================

async def upload_variant(
    storage_path_base: str,
    variant: ProcessedVariant,
) -> str:
    """
    Upload a processed variant to Supabase Storage.

    Args:
        storage_path_base: Base path without extension (e.g., photos/tenant/acc/general/uuid)
        variant: The processed variant to upload

    Returns:
        Public URL of the uploaded variant
    """
    client = get_supabase_client()

    # Construct path: base_size.format
    ext = "avif" if variant.format == "avif" else "webp"
    variant_path = f"{storage_path_base}_{variant.size_name}.{ext}"

    # Upload to bucket
    result = client.storage.from_(BUCKET_NAME).upload(
        path=variant_path,
        file=variant.data,
        file_options={
            "content-type": variant.content_type,
            "cache-control": "31536000",  # 1 year cache for immutable variants
        },
    )

    if hasattr(result, "error") and result.error:
        raise Exception(f"Upload variant failed: {result.error}")

    # Get public URL
    public_url = client.storage.from_(BUCKET_NAME).get_public_url(variant_path)

    return public_url


async def process_photo(
    db: AsyncSession,
    photo: AccommodationPhoto,
) -> bool:
    """
    Process a single photo: download original, process, upload variants, update DB.

    Args:
        db: Database session
        photo: The photo record to process

    Returns:
        True if processing succeeded
    """
    try:
        logger.info(f"Processing photo {photo.id} (accommodation {photo.accommodation_id})")

        client = get_supabase_client()

        # Download original image
        response = client.storage.from_(BUCKET_NAME).download(photo.storage_path)

        if not response:
            logger.error(f"Failed to download original for photo {photo.id}")
            return False

        # Process image
        result = process_image(response)

        # Extract base path (remove extension)
        base_path = photo.storage_path.rsplit(".", 1)[0]

        # Upload variants
        url_avif = None
        url_webp = None
        url_medium = None
        url_large = None
        srcset_entries = []

        for variant in result.variants:
            url = await upload_variant(base_path, variant)

            # Store main URLs
            if variant.format == "avif":
                if variant.size_name == "large":
                    url_large = url
                elif variant.size_name == "medium":
                    url_medium = url
                    url_avif = url  # Use medium as main AVIF
            elif variant.format == "webp":
                if variant.size_name == "medium":
                    url_webp = url

            # Build srcset entry
            srcset_entries.append({
                "url": url,
                "width": variant.width,
                "format": variant.format,
                "size": variant.size_name,
            })

        # Upload thumbnail (JPEG for maximum compatibility)
        from app.services.image_processor import resize_image, save_as_jpeg, SIZES
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(response))
        thumbnail = resize_image(img, SIZES["thumbnail"])
        thumbnail_data = save_as_jpeg(thumbnail, 75)

        thumbnail_path = f"{base_path}_thumbnail.jpg"
        client.storage.from_(BUCKET_NAME).upload(
            path=thumbnail_path,
            file=thumbnail_data,
            file_options={
                "content-type": "image/jpeg",
                "cache-control": "31536000",
            },
        )
        thumbnail_url = client.storage.from_(BUCKET_NAME).get_public_url(thumbnail_path)

        # Update photo record
        photo.thumbnail_url = thumbnail_url
        photo.url_avif = url_avif
        photo.url_webp = url_webp
        photo.url_medium = url_medium
        photo.url_large = url_large
        photo.lqip_data_url = result.lqip_data_url
        photo.srcset_json = json.dumps(srcset_entries)
        photo.width = result.original_width
        photo.height = result.original_height
        photo.is_processed = True
        photo.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(f"Successfully processed photo {photo.id}")
        return True

    except Exception as e:
        logger.exception(f"Error processing photo {photo.id}: {e}")
        await db.rollback()
        return False


async def process_unprocessed_photos(
    db: AsyncSession,
    limit: int = 10,
) -> int:
    """
    Find and process unprocessed photos.

    Args:
        db: Database session
        limit: Maximum number of photos to process in this batch

    Returns:
        Number of photos successfully processed
    """
    # Find unprocessed photos
    stmt = (
        select(AccommodationPhoto)
        .where(AccommodationPhoto.is_processed == False)
        .order_by(AccommodationPhoto.created_at.asc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    photos = result.scalars().all()

    if not photos:
        logger.info("No unprocessed photos found")
        return 0

    logger.info(f"Found {len(photos)} unprocessed photos")

    processed_count = 0
    for photo in photos:
        success = await process_photo(db, photo)
        if success:
            processed_count += 1

    return processed_count


async def run_worker_once(db: AsyncSession, batch_size: int = 10) -> int:
    """
    Run the worker once to process a batch of photos.

    Args:
        db: Database session
        batch_size: Number of photos to process

    Returns:
        Number of photos processed
    """
    return await process_unprocessed_photos(db, limit=batch_size)


async def run_worker_loop(
    get_db_session,
    batch_size: int = 10,
    interval_seconds: int = 30,
):
    """
    Run the worker in a continuous loop.

    Args:
        get_db_session: Async generator that yields database sessions
        batch_size: Number of photos to process per batch
        interval_seconds: Seconds to wait between batches
    """
    logger.info("Starting image processing worker loop")

    while True:
        try:
            async for db in get_db_session():
                processed = await process_unprocessed_photos(db, limit=batch_size)
                if processed > 0:
                    logger.info(f"Processed {processed} photos in this batch")
                break

        except Exception as e:
            logger.exception(f"Error in worker loop: {e}")

        await asyncio.sleep(interval_seconds)


# ============================================================================
# Synchronous Processing (for immediate processing on upload)
# ============================================================================

async def process_photo_immediately(
    db: AsyncSession,
    photo_id: int,
) -> bool:
    """
    Process a specific photo immediately (called after upload).

    Args:
        db: Database session
        photo_id: ID of the photo to process

    Returns:
        True if processing succeeded
    """
    stmt = select(AccommodationPhoto).where(AccommodationPhoto.id == photo_id)
    result = await db.execute(stmt)
    photo = result.scalar_one_or_none()

    if not photo:
        logger.error(f"Photo {photo_id} not found")
        return False

    if photo.is_processed:
        logger.info(f"Photo {photo_id} already processed")
        return True

    return await process_photo(db, photo)
