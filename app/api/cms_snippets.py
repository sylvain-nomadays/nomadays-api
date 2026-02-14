"""
CMS Snippets API — CRUD + resolution for editable UI content.

Endpoints:
  GET    /cms/snippets              — List snippets (by category, tenant-scoped)
  GET    /cms/snippets/resolve      — Resolve snippets with tenant→global→null cascade
  GET    /cms/snippets/{key}        — Get single snippet by key
  PUT    /cms/snippets/{key}        — Upsert a snippet
  DELETE /cms/snippets/{key}        — Delete a snippet
  POST   /cms/snippets/batch        — Batch upsert multiple snippets
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, TenantId, DbSession
from app.models.cms_snippet import CmsSnippet

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class SnippetOut(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    snippet_key: str
    category: str
    content_json: dict
    metadata_json: Optional[dict] = None
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_instance(cls, obj: CmsSnippet) -> "SnippetOut":
        return cls(
            id=str(obj.id),
            tenant_id=str(obj.tenant_id) if obj.tenant_id else None,
            snippet_key=obj.snippet_key,
            category=obj.category,
            content_json=obj.content_json or {},
            metadata_json=obj.metadata_json,
            is_active=obj.is_active,
            sort_order=obj.sort_order,
        )


class SnippetUpsert(BaseModel):
    category: str = Field(..., max_length=30)
    content_json: dict = Field(default_factory=dict)
    metadata_json: Optional[dict] = None
    is_active: bool = True
    sort_order: int = 0


class SnippetBatchItem(BaseModel):
    snippet_key: str = Field(..., max_length=100)
    category: str = Field(..., max_length=30)
    content_json: dict = Field(default_factory=dict)
    metadata_json: Optional[dict] = None
    is_active: bool = True
    sort_order: int = 0


class SnippetBatchRequest(BaseModel):
    snippets: list[SnippetBatchItem]


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/cms/snippets", response_model=list[SnippetOut])
async def list_snippets(
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
    category: Optional[str] = Query(None, description="Filter by category"),
    include_global: bool = Query(False, description="Also include global snippets"),
):
    """List snippets for the current tenant, optionally filtered by category."""
    conditions = []

    if include_global:
        conditions.append(
            or_(CmsSnippet.tenant_id == tenant_id, CmsSnippet.tenant_id.is_(None))
        )
    else:
        conditions.append(CmsSnippet.tenant_id == tenant_id)

    if category:
        conditions.append(CmsSnippet.category == category)

    conditions.append(CmsSnippet.is_active.is_(True))

    query = (
        select(CmsSnippet)
        .where(and_(*conditions))
        .order_by(CmsSnippet.category, CmsSnippet.sort_order, CmsSnippet.snippet_key)
    )

    result = await db.execute(query)
    snippets = result.scalars().all()
    return [SnippetOut.from_orm_instance(s) for s in snippets]


@router.get("/cms/snippets/resolve")
async def resolve_snippets(
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
    keys: str = Query(..., description="Comma-separated snippet keys"),
    lang: str = Query("fr", description="Language code (fr, en, etc.)"),
):
    """
    Resolve snippets with cascade: tenant-specific → global → null.
    Returns a dict of {key: content_in_lang}.
    """
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list:
        return {}

    # Fetch all matching snippets (both tenant-specific and global)
    query = (
        select(CmsSnippet)
        .where(
            and_(
                CmsSnippet.snippet_key.in_(key_list),
                CmsSnippet.is_active.is_(True),
                or_(CmsSnippet.tenant_id == tenant_id, CmsSnippet.tenant_id.is_(None)),
            )
        )
    )
    result = await db.execute(query)
    snippets = result.scalars().all()

    # Build resolution: tenant-specific wins over global
    resolved: dict[str, str] = {}
    global_snippets: dict[str, CmsSnippet] = {}
    tenant_snippets: dict[str, CmsSnippet] = {}

    for s in snippets:
        if s.tenant_id == tenant_id:
            tenant_snippets[s.snippet_key] = s
        elif s.tenant_id is None:
            global_snippets[s.snippet_key] = s

    for key in key_list:
        snippet = tenant_snippets.get(key) or global_snippets.get(key)
        if snippet and snippet.content_json:
            resolved[key] = snippet.content_json.get(lang, snippet.content_json.get("fr", ""))
        else:
            resolved[key] = ""

    return resolved


@router.get("/cms/snippets/resolve-full")
async def resolve_snippets_full(
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
    category: str = Query(..., description="Category to resolve"),
    lang: str = Query("fr", description="Language code"),
):
    """
    Resolve all snippets of a category with full metadata.
    Used by admin editors and client-side data fetching.
    Returns full snippet objects with tenant→global cascade applied.
    """
    query = (
        select(CmsSnippet)
        .where(
            and_(
                CmsSnippet.category == category,
                CmsSnippet.is_active.is_(True),
                or_(CmsSnippet.tenant_id == tenant_id, CmsSnippet.tenant_id.is_(None)),
            )
        )
        .order_by(CmsSnippet.sort_order, CmsSnippet.snippet_key)
    )
    result = await db.execute(query)
    snippets = result.scalars().all()

    # Build resolution: tenant-specific wins over global
    resolved: dict[str, CmsSnippet] = {}
    for s in snippets:
        key = s.snippet_key
        if s.tenant_id is not None:
            # Tenant-specific always wins
            resolved[key] = s
        elif key not in resolved:
            # Global only if no tenant-specific exists
            resolved[key] = s

    return [SnippetOut.from_orm_instance(s) for s in sorted(resolved.values(), key=lambda x: (x.sort_order, x.snippet_key))]


@router.get("/cms/snippets/{key}", response_model=SnippetOut)
async def get_snippet(
    key: str,
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
):
    """Get a single snippet by key (tenant-scoped)."""
    query = select(CmsSnippet).where(
        and_(CmsSnippet.snippet_key == key, CmsSnippet.tenant_id == tenant_id)
    )
    result = await db.execute(query)
    snippet = result.scalar_one_or_none()

    if not snippet:
        # Fallback to global
        query = select(CmsSnippet).where(
            and_(CmsSnippet.snippet_key == key, CmsSnippet.tenant_id.is_(None))
        )
        result = await db.execute(query)
        snippet = result.scalar_one_or_none()

    if not snippet:
        raise HTTPException(status_code=404, detail=f"Snippet '{key}' not found")

    return SnippetOut.from_orm_instance(snippet)


@router.put("/cms/snippets/{key}", response_model=SnippetOut)
async def upsert_snippet(
    key: str,
    body: SnippetUpsert,
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
):
    """Create or update a snippet for the current tenant."""
    # Check if exists
    query = select(CmsSnippet).where(
        and_(CmsSnippet.snippet_key == key, CmsSnippet.tenant_id == tenant_id)
    )
    result = await db.execute(query)
    snippet = result.scalar_one_or_none()

    if snippet:
        # Update
        snippet.category = body.category
        snippet.content_json = body.content_json
        snippet.metadata_json = body.metadata_json
        snippet.is_active = body.is_active
        snippet.sort_order = body.sort_order
    else:
        # Create
        snippet = CmsSnippet(
            tenant_id=tenant_id,
            snippet_key=key,
            category=body.category,
            content_json=body.content_json,
            metadata_json=body.metadata_json,
            is_active=body.is_active,
            sort_order=body.sort_order,
        )
        db.add(snippet)

    await db.commit()
    await db.refresh(snippet)
    return SnippetOut.from_orm_instance(snippet)


@router.delete("/cms/snippets/{key}", status_code=204)
async def delete_snippet(
    key: str,
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
):
    """Delete a snippet for the current tenant."""
    query = delete(CmsSnippet).where(
        and_(CmsSnippet.snippet_key == key, CmsSnippet.tenant_id == tenant_id)
    )
    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Snippet '{key}' not found")


@router.post("/cms/snippets/batch", response_model=list[SnippetOut])
async def batch_upsert_snippets(
    body: SnippetBatchRequest,
    user: CurrentUser,
    tenant_id: TenantId,
    db: DbSession,
):
    """Batch create/update multiple snippets for the current tenant."""
    results = []

    for item in body.snippets:
        # Check if exists
        query = select(CmsSnippet).where(
            and_(
                CmsSnippet.snippet_key == item.snippet_key,
                CmsSnippet.tenant_id == tenant_id,
            )
        )
        result = await db.execute(query)
        snippet = result.scalar_one_or_none()

        if snippet:
            snippet.category = item.category
            snippet.content_json = item.content_json
            snippet.metadata_json = item.metadata_json
            snippet.is_active = item.is_active
            snippet.sort_order = item.sort_order
        else:
            snippet = CmsSnippet(
                tenant_id=tenant_id,
                snippet_key=item.snippet_key,
                category=item.category,
                content_json=item.content_json,
                metadata_json=item.metadata_json,
                is_active=item.is_active,
                sort_order=item.sort_order,
            )
            db.add(snippet)

        results.append(snippet)

    await db.commit()

    # Refresh all
    for s in results:
        await db.refresh(s)

    return [SnippetOut.from_orm_instance(s) for s in results]
