"""
Administrative Audit Logging & Security Observability Endpoints.
Provides strictly RBAC-protected (require_admin) REST APIs for querying immutable audit trails,
inspecting individual compliance events, and retrieving aggregated security telemetry.
"""
from datetime import datetime
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import require_admin
from backend.app.core.config import settings
from backend.app.db.models.audit_event import AuditEvent
from backend.app.db.session import get_db
from backend.app.schemas.audit import (
    AuditEventListResponse,
    AuditEventResponse,
    AuditEventType,
    AuditQueryFilter,
    AuditSeverity,
    AuditStatisticsResponse,
    AuthorizationResult,
)
from backend.app.schemas.auth import RBACContext
from backend.app.services.audit_service import audit_service

router = APIRouter()


@router.get(
    "/events",
    response_model=AuditEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query audit events (Admin Only)",
    description=(
        "Returns a paginated list of structured audit and security events. "
        "Strictly accessible only by users possessing the Admin role (clearance L4)."
    ),
)
async def list_audit_events(
    event_type: Optional[AuditEventType] = Query(None, description="Filter by event type"),
    severity: Optional[AuditSeverity] = Query(None, description="Filter by severity level"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by actor user UUID"),
    request_id: Optional[str] = Query(None, max_length=64, description="Filter by correlation request ID"),
    resource_type: Optional[str] = Query(None, max_length=64, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, max_length=255, description="Filter by resource identifier"),
    authorization_result: Optional[AuthorizationResult] = Query(None, description="Filter by authorization outcome"),
    start_time: Optional[datetime] = Query(None, description="Inclusive start timestamp filter"),
    end_time: Optional[datetime] = Query(None, description="Inclusive end timestamp filter"),
    limit: int = Query(default=50, ge=1, le=100, description="Pagination record limit"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    admin_rbac: RBACContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditEventListResponse:
    """Queries audit events using structured filters with server-authoritative admin authorization."""
    if start_time and end_time and end_time < start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be greater than or equal to start_time.",
        )

    filter_spec = AuditQueryFilter(
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        request_id=request_id,
        resource_type=resource_type,
        resource_id=resource_id,
        authorization_result=authorization_result,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    events, total = await audit_service.query_events(filter_spec, db)
    items = [AuditEventResponse.model_validate(e) for e in events]

    return AuditEventListResponse(
        items=items,
        total=total,
        limit=filter_spec.limit,
        offset=filter_spec.offset,
    )


@router.get(
    "/events/{event_id}",
    response_model=AuditEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Get audit event by ID (Admin Only)",
    description="Retrieves a single audit event record by its primary UUID.",
)
async def get_audit_event(
    event_id: uuid.UUID,
    admin_rbac: RBACContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditEventResponse:
    """Retrieves an individual audit record."""
    stmt = select(AuditEvent).where(AuditEvent.id == event_id)
    res = await db.execute(stmt)
    event = res.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit event with ID '{event_id}' was not found.",
        )

    return AuditEventResponse.model_validate(event)


@router.get(
    "/statistics",
    response_model=AuditStatisticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get audit & security statistics (Admin Only)",
    description="Returns aggregate compliance metrics and anomaly statistics across the specified time window.",
)
async def get_audit_statistics(
    start_time: Optional[datetime] = Query(None, description="Start timestamp of analytics window"),
    end_time: Optional[datetime] = Query(None, description="End timestamp of analytics window"),
    admin_rbac: RBACContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditStatisticsResponse:
    """Computes aggregated security and operational metrics."""
    if start_time and end_time and end_time < start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be greater than or equal to start_time.",
        )

    return await audit_service.get_statistics(start_time=start_time, end_time=end_time, db=db)
