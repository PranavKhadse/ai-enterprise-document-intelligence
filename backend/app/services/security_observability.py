"""
Phase 11 Deterministic Security Observability & Anomaly Detection Service.
Implements bounded, rule-based detection for repeated authentication failures,
authorization denial bursts, and access anomaly patterns without external ML or SIEM dependencies.
"""
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Union
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.models.audit_event import AuditEvent
from backend.app.db.session import AsyncSessionLocal
from backend.app.schemas.audit import AuditEventType, AuditSeverity
from backend.app.services.audit_service import audit_service

logger = logging.getLogger(__name__)


class SecurityObservabilityService:
    """
    Deterministic rule-based security anomaly detection engine.
    Scans recent audit events within sliding time windows to identify suspicious activity bursts.
    """

    def __init__(
        self,
        failure_threshold: Optional[int] = None,
        window_minutes: Optional[int] = None,
    ):
        self.failure_threshold = failure_threshold or settings.AUDIT_SECURITY_FAILURE_THRESHOLD
        self.window_minutes = window_minutes or settings.AUDIT_SECURITY_WINDOW_MINUTES

    async def evaluate_login_failure_anomaly(
        self,
        target_identity: str,
        source_ip: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """
        Evaluates whether repeated authentication failures exceed the security threshold
        within the sliding time window, generating a HIGH-severity SECURITY_EVENT if detected.
        """
        if not target_identity and not source_ip:
            return None

        clean_identity = target_identity.strip().lower() if target_identity else None
        now_dt = datetime.now(timezone.utc)
        window_start = now_dt - timedelta(minutes=self.window_minutes)

        async def _check(session: AsyncSession) -> Optional[AuditEvent]:
            # Count recent login failures for this email or IP
            stmt = select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == AuditEventType.AUTH_LOGIN_FAILURE.value,
                AuditEvent.created_at >= window_start,
            )
            if clean_identity:
                stmt = stmt.where(AuditEvent.resource_id == clean_identity)
            elif source_ip:
                stmt = stmt.where(AuditEvent.source_ip == source_ip)

            res = await session.execute(stmt)
            failure_count = res.scalar_one()

            if failure_count >= self.failure_threshold:
                # Check if a security event was already recorded for this target in current window
                sec_check = select(func.count(AuditEvent.id)).where(
                    AuditEvent.event_type == AuditEventType.SECURITY_EVENT.value,
                    AuditEvent.action == "login_failure_threshold_exceeded",
                    AuditEvent.resource_id == (clean_identity or source_ip),
                    AuditEvent.created_at >= window_start,
                )
                sec_res = await session.execute(sec_check)
                if sec_res.scalar_one() == 0:
                    # Emit new Security Event
                    return await audit_service.record_event(
                        event_type=AuditEventType.SECURITY_EVENT,
                        action="login_failure_threshold_exceeded",
                        severity=AuditSeverity.HIGH,
                        resource_type="authentication",
                        resource_id=clean_identity or source_ip,
                        source_ip=source_ip,
                        metadata={
                            "failure_count": failure_count,
                            "threshold": self.failure_threshold,
                            "window_minutes": self.window_minutes,
                            "target_identity": clean_identity,
                        },
                        db=session,
                    )
            return None

        if db is not None:
            return await _check(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _check(session)

    async def evaluate_authorization_denial_anomaly(
        self,
        user_id: Optional[uuid.UUID] = None,
        email: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """
        Evaluates whether repeated authorization denials exceed the security threshold
        for a user within the sliding time window, generating a HIGH-severity SECURITY_EVENT.
        """
        if not user_id and not email:
            return None

        now_dt = datetime.now(timezone.utc)
        window_start = now_dt - timedelta(minutes=self.window_minutes)

        async def _check(session: AsyncSession) -> Optional[AuditEvent]:
            stmt = select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == AuditEventType.AUTHORIZATION_DENIED.value,
                AuditEvent.created_at >= window_start,
            )
            if user_id:
                stmt = stmt.where(AuditEvent.user_id == user_id)
            elif email:
                stmt = stmt.where(AuditEvent.email == email.strip().lower())

            res = await session.execute(stmt)
            denial_count = res.scalar_one()

            if denial_count >= self.failure_threshold:
                target_id_str = str(user_id) if user_id else (email or "unknown")
                sec_check = select(func.count(AuditEvent.id)).where(
                    AuditEvent.event_type == AuditEventType.SECURITY_EVENT.value,
                    AuditEvent.action == "authorization_denial_threshold_exceeded",
                    AuditEvent.resource_id == target_id_str,
                    AuditEvent.created_at >= window_start,
                )
                sec_res = await session.execute(sec_check)
                if sec_res.scalar_one() == 0:
                    return await audit_service.record_event(
                        event_type=AuditEventType.SECURITY_EVENT,
                        action="authorization_denial_threshold_exceeded",
                        severity=AuditSeverity.HIGH,
                        resource_type="authorization",
                        resource_id=target_id_str,
                        metadata={
                            "denial_count": denial_count,
                            "threshold": self.failure_threshold,
                            "window_minutes": self.window_minutes,
                            "user_id": str(user_id) if user_id else None,
                        },
                        db=session,
                    )
            return None

        if db is not None:
            return await _check(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _check(session)


# Global singleton instance
security_observability = SecurityObservabilityService()
