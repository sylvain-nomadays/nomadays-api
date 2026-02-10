"""
Supabase Storage service for file uploads.

Handles uploading, deleting, and managing files in Supabase Storage.
Organized by tenant for multi-tenant isolation.
"""

import uuid
import os
from typing import Optional, Tuple
from pathlib import Path

from supabase import create_client, Client
from app.config import get_settings

# Bucket name for images
BUCKET_NAME = "nomadays-images"

# Allowed MIME types for images
ALLOWED_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/avif",
    "image/gif",
]

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# MIME type to extension mapping
MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/gif": ".gif",
}


def get_supabase_client() -> Client:
    """Get Supabase client with service role key for storage operations."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


def get_mime_type(filename: str) -> str:
    """Get MIME type from filename extension."""
    ext = Path(filename).suffix.lower()
    ext_to_mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".avif": "image/avif",
        ".gif": "image/gif",
    }
    return ext_to_mime.get(ext, "application/octet-stream")


def validate_file(
    file_content: bytes,
    filename: str,
    mime_type: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Validate an uploaded file.

    Returns (is_valid, error_message).
    """
    # Check file size
    if len(file_content) > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"

    # Check MIME type
    actual_mime = mime_type or get_mime_type(filename)
    if actual_mime not in ALLOWED_MIME_TYPES:
        return False, f"Invalid file type. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"

    return True, ""


async def upload_to_supabase(
    file_content: bytes,
    original_filename: str,
    tenant_id: str,
    accommodation_id: int,
    room_category_id: Optional[int] = None,
    mime_type: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Upload a file to Supabase Storage.

    Args:
        file_content: The file bytes
        original_filename: Original filename for extension detection
        tenant_id: Tenant UUID for folder organization
        accommodation_id: Accommodation ID for folder organization
        room_category_id: Optional room category ID (NULL = hotel-level photo)
        mime_type: Optional MIME type override

    Returns:
        Tuple of (storage_path, public_url)
    """
    client = get_supabase_client()

    # Validate file
    is_valid, error = validate_file(file_content, original_filename, mime_type)
    if not is_valid:
        raise ValueError(error)

    # Determine file extension
    actual_mime = mime_type or get_mime_type(original_filename)
    ext = MIME_TO_EXT.get(actual_mime, Path(original_filename).suffix.lower())

    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}{ext}"

    # Build storage path
    # photos/{tenant_id}/{accommodation_id}/{room_category_id or 'general'}/{filename}
    category_folder = f"room_{room_category_id}" if room_category_id else "general"
    storage_path = f"photos/{tenant_id}/{accommodation_id}/{category_folder}/{unique_filename}"

    # Upload to bucket
    result = client.storage.from_(BUCKET_NAME).upload(
        path=storage_path,
        file=file_content,
        file_options={
            "content-type": actual_mime,
            "cache-control": "3600",  # 1 hour cache
        },
    )

    # Check for errors
    if hasattr(result, "error") and result.error:
        raise Exception(f"Upload failed: {result.error}")

    # Get public URL
    public_url = client.storage.from_(BUCKET_NAME).get_public_url(storage_path)

    return storage_path, public_url


async def delete_from_supabase(storage_path: str) -> bool:
    """
    Delete a file from Supabase Storage.

    Args:
        storage_path: The path of the file in storage

    Returns:
        True if deletion was successful
    """
    client = get_supabase_client()

    result = client.storage.from_(BUCKET_NAME).remove([storage_path])

    # Check for errors
    if hasattr(result, "error") and result.error:
        raise Exception(f"Delete failed: {result.error}")

    return True


async def delete_multiple_from_supabase(storage_paths: list[str]) -> bool:
    """
    Delete multiple files from Supabase Storage.

    Args:
        storage_paths: List of paths to delete

    Returns:
        True if deletion was successful
    """
    if not storage_paths:
        return True

    client = get_supabase_client()

    result = client.storage.from_(BUCKET_NAME).remove(storage_paths)

    # Check for errors
    if hasattr(result, "error") and result.error:
        raise Exception(f"Delete failed: {result.error}")

    return True


def get_public_url(storage_path: str) -> str:
    """
    Get the public URL for a file in storage.

    Args:
        storage_path: The path of the file in storage

    Returns:
        Public URL of the file
    """
    client = get_supabase_client()
    return client.storage.from_(BUCKET_NAME).get_public_url(storage_path)


# SQL for creating the bucket in Supabase (run manually or via migration)
BUCKET_SETUP_SQL = """
-- Create bucket for images (run in Supabase SQL Editor)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'nomadays-images',
    'nomadays-images',
    true,  -- Public bucket for CDN access
    10485760,  -- 10MB max
    ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/avif', 'image/gif']
)
ON CONFLICT (id) DO NOTHING;

-- RLS Policy: Allow authenticated uploads
CREATE POLICY IF NOT EXISTS "Authenticated users can upload photos"
ON storage.objects FOR INSERT
WITH CHECK (
    bucket_id = 'nomadays-images' AND
    auth.role() = 'authenticated'
);

-- RLS Policy: Public read access
CREATE POLICY IF NOT EXISTS "Public read access for photos"
ON storage.objects FOR SELECT
USING (bucket_id = 'nomadays-images');

-- RLS Policy: Allow authenticated deletes
CREATE POLICY IF NOT EXISTS "Authenticated users can delete their photos"
ON storage.objects FOR DELETE
USING (
    bucket_id = 'nomadays-images' AND
    auth.role() = 'authenticated'
);
"""
