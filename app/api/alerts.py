"""
AI Alerts endpoints - for price anomaly detection dashboard.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.alert import AIAlert

router = APIRouter()


# Schemas
class AlertResponse(BaseModel):
    id: int
    item_id: int
    item_name: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    expected_value: Optional[float]
    actual_value: Optional[float]
    deviation_pct: Optional[float]
    acknowledged: bool
    acknowledged_at: Optional[datetime]
    acknowledged_by_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    items: List[AlertResponse]
    total: int
    unacknowledged_count: int


class AlertAcknowledge(BaseModel):
    acknowledged: bool = True


class AlertStats(BaseModel):
    total: int
    unacknowledged: int
    by_severity: dict
    by_type: dict


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    db: DbSession,
    tenant: CurrentTenant,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    item_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List AI alerts for the tenant.
    """
    query = select(AIAlert).where(AIAlert.tenant_id == tenant.id)

    # Filters
    if severity:
        query = query.where(AIAlert.severity == severity)
    if alert_type:
        query = query.where(AIAlert.alert_type == alert_type)
    if acknowledged is not None:
        query = query.where(AIAlert.acknowledged == acknowledged)
    if item_id:
        query = query.where(AIAlert.item_id == item_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Count unacknowledged
    unack_query = select(func.count()).where(
        AIAlert.tenant_id == tenant.id,
        AIAlert.acknowledged == False,
    )
    unack_count = (await db.execute(unack_query)).scalar()

    # Pagination and ordering
    query = query.order_by(AIAlert.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    alerts = result.scalars().all()

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        unacknowledged_count=unack_count,
    )


@router.get("/stats", response_model=AlertStats)
async def get_alert_stats(
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get alert statistics for the dashboard.
    """
    # Total
    total_query = select(func.count()).where(AIAlert.tenant_id == tenant.id)
    total = (await db.execute(total_query)).scalar()

    # Unacknowledged
    unack_query = select(func.count()).where(
        AIAlert.tenant_id == tenant.id,
        AIAlert.acknowledged == False,
    )
    unacknowledged = (await db.execute(unack_query)).scalar()

    # By severity
    severity_query = (
        select(AIAlert.severity, func.count())
        .where(AIAlert.tenant_id == tenant.id)
        .group_by(AIAlert.severity)
    )
    severity_result = await db.execute(severity_query)
    by_severity = {row[0]: row[1] for row in severity_result}

    # By type
    type_query = (
        select(AIAlert.alert_type, func.count())
        .where(AIAlert.tenant_id == tenant.id)
        .group_by(AIAlert.alert_type)
    )
    type_result = await db.execute(type_query)
    by_type = {row[0]: row[1] for row in type_result}

    return AlertStats(
        total=total,
        unacknowledged=unacknowledged,
        by_severity=by_severity,
        by_type=by_type,
    )


@router.patch("/{alert_id}", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    data: AlertAcknowledge,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Acknowledge or un-acknowledge an alert.
    """
    result = await db.execute(
        select(AIAlert).where(
            AIAlert.id == alert_id,
            AIAlert.tenant_id == tenant.id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    alert.acknowledged = data.acknowledged
    if data.acknowledged:
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by_id = user.id
    else:
        alert.acknowledged_at = None
        alert.acknowledged_by_id = None

    await db.commit()
    await db.refresh(alert)

    return AlertResponse.model_validate(alert)


@router.post("/acknowledge-all")
async def acknowledge_all_alerts(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    severity: Optional[str] = None,
):
    """
    Acknowledge all unacknowledged alerts (optionally filtered by severity).
    """
    query = select(AIAlert).where(
        AIAlert.tenant_id == tenant.id,
        AIAlert.acknowledged == False,
    )

    if severity:
        query = query.where(AIAlert.severity == severity)

    result = await db.execute(query)
    alerts = result.scalars().all()

    now = datetime.utcnow()
    for alert in alerts:
        alert.acknowledged = True
        alert.acknowledged_at = now
        alert.acknowledged_by_id = user.id

    await db.commit()

    return {"acknowledged_count": len(alerts)}
