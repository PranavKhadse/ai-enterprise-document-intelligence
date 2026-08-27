"""
Unit tests for SecurityObservabilityService.
Verifies threshold-based anomaly detection for repeated authentication failures
and authorization denial bursts.
"""
from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models.audit_event import AuditEvent
from backend.app.schemas.audit import AuditEventType, AuditSeverity, AuthorizationResult
from backend.app.services.audit_service import audit_service
from backend.app.services.security_observability import SecurityObservabilityService


@pytest.fixture
async def sec_db():
    """Provides an isolated in-memory SQLite database for security observability testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_login_failure_anomaly_threshold_detection(sec_db):
    """Verifies that reaching the failed login threshold emits a HIGH-severity SECURITY_EVENT."""
    obs_service = SecurityObservabilityService(failure_threshold=5, window_minutes=10)
    target_email = "target.user@enterprise.com"

    # Simulate 4 failed login attempts (below threshold)
    for _ in range(4):
        await audit_service.record_auth_failure(
            attempted_email=target_email,
            source_ip="192.168.1.100",
            db=sec_db,
        )
        sec_event = await obs_service.evaluate_login_failure_anomaly(
            target_identity=target_email,
            source_ip="192.168.1.100",
            db=sec_db,
        )
        assert sec_event is None  # Below threshold

    # 5th failed login attempt (reaches threshold)
    await audit_service.record_auth_failure(
        attempted_email=target_email,
        source_ip="192.168.1.100",
        db=sec_db,
    )
    sec_event = await obs_service.evaluate_login_failure_anomaly(
        target_identity=target_email,
        source_ip="192.168.1.100",
        db=sec_db,
    )

    assert sec_event is not None
    assert sec_event.event_type == AuditEventType.SECURITY_EVENT.value
    assert sec_event.severity == AuditSeverity.HIGH.value
    assert sec_event.action == "login_failure_threshold_exceeded"
    assert sec_event.resource_id == target_email
    assert sec_event.metadata_json["failure_count"] >= 5


@pytest.mark.asyncio
async def test_authorization_denial_anomaly_detection(sec_db):
    """Verifies that repeated authorization denials for a user emit a SECURITY_EVENT."""
    obs_service = SecurityObservabilityService(failure_threshold=3, window_minutes=10)
    user_id = uuid.uuid4()

    # 2 denials (below threshold)
    for _ in range(2):
        await audit_service.record_authorization_denied(
            principal={"user_id": user_id, "email": "dev@corp.com", "roles": ["Employee"], "clearance_level": 1},
            action="access_hr_salaries",
            resource_type="document",
            resource_id="doc-salary-2026",
            db=sec_db,
        )
        sec_ev = await obs_service.evaluate_authorization_denial_anomaly(user_id=user_id, db=sec_db)
        assert sec_ev is None

    # 3rd denial (triggers threshold)
    await audit_service.record_authorization_denied(
        principal={"user_id": user_id, "email": "dev@corp.com", "roles": ["Employee"], "clearance_level": 1},
        action="access_hr_salaries",
        resource_type="document",
        resource_id="doc-salary-2026",
        db=sec_db,
    )
    sec_ev = await obs_service.evaluate_authorization_denial_anomaly(user_id=user_id, db=sec_db)

    assert sec_ev is not None
    assert sec_ev.event_type == AuditEventType.SECURITY_EVENT.value
    assert sec_ev.severity == AuditSeverity.HIGH.value
    assert sec_ev.action == "authorization_denial_threshold_exceeded"
    assert sec_ev.resource_id == str(user_id)
