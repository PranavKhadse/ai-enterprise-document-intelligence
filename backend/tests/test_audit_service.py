"""
Unit and Integration tests for AuditService.
Verifies recursive secret redaction, JWT/Bearer sanitization, deterministic query fingerprinting,
tamper-evident hash chaining, and database query filtering.
"""
from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.models.audit_event import AuditEvent
from backend.app.schemas.audit import AuditEventType, AuditQueryFilter, AuditSeverity, AuthorizationResult
from backend.app.services.audit_service import (
    AuditService,
    compute_canonical_event_hash,
    generate_query_fingerprint,
    sanitize_metadata,
)


@pytest.fixture
async def audit_db():
    """Provides an isolated in-memory SQLite database for audit service testing."""
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


def test_recursive_secret_redaction():
    """Verifies that nested passwords, API keys, and credentials are recursively redacted."""
    raw_payload = {
        "user_email": "alice@corp.com",
        "nested": {
            "password": "SuperSecretPassword123!",
            "api_key": "sk-proj-1234567890",
            "safe_param": 42,
            "deep": {
                "access_token": "token_abc_xyz",
                "refresh_token": "refresh_xyz",
                "normal_list": ["item1", {"private_key": "PEM_SECRET_KEY"}],
            },
        },
        "credentials": {"db_secret": "my_secret_pass"},
    }

    sanitized = sanitize_metadata(raw_payload)

    assert sanitized["user_email"] == "alice@corp.com"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["safe_param"] == 42
    assert sanitized["nested"]["deep"]["access_token"] == "[REDACTED]"
    assert sanitized["nested"]["deep"]["refresh_token"] == "[REDACTED]"
    assert sanitized["nested"]["deep"]["normal_list"][0] == "item1"
    assert sanitized["nested"]["deep"]["normal_list"][1]["private_key"] == "[REDACTED]"
    assert sanitized["credentials"] == "[REDACTED]"


def test_embedded_jwt_and_bearer_redaction():
    """Verifies that strings containing embedded JWT tokens and Bearer tokens are redacted."""
    dummy_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doz_dummy_sig_12345"
    raw_payload = {
        "auth_header": f"Bearer {dummy_jwt}",
        "raw_message": f"User presented token: {dummy_jwt} during request",
        "plain_text": "Normal operational text without tokens",
    }

    sanitized = sanitize_metadata(raw_payload)

    assert "Bearer [REDACTED]" in sanitized["auth_header"]
    assert "[REDACTED_JWT]" in sanitized["raw_message"]
    assert dummy_jwt not in sanitized["raw_message"]
    assert sanitized["plain_text"] == "Normal operational text without tokens"


def test_deterministic_query_fingerprinting():
    """Verifies that query fingerprints are deterministic and normalize case and whitespace."""
    q1 = "What is the mandatory authentication policy?"
    q2 = "  what   is  the MANDATORY authentication policy? "
    q3 = "What is the data retention period?"

    fp1 = generate_query_fingerprint(q1)
    fp2 = generate_query_fingerprint(q2)
    fp3 = generate_query_fingerprint(q3)

    assert fp1 is not None
    assert fp1.startswith("sha256:")
    assert fp1 == fp2  # Normalized identical queries produce identical fingerprints
    assert fp1 != fp3  # Different queries produce different fingerprints
    assert generate_query_fingerprint(None) is None
    assert generate_query_fingerprint("   ") is None


@pytest.mark.asyncio
async def test_audit_event_creation_and_querying(audit_db):
    """Verifies that audit events are persisted and queryable with structured filters."""
    service = AuditService()
    user_id = uuid.uuid4()

    # Record 3 events
    ev1 = await service.record_event(
        event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
        action="login",
        severity=AuditSeverity.INFO,
        principal={"user_id": user_id, "email": "user1@enterprise.com", "roles": ["Employee"], "clearance_level": 1},
        resource_type="user",
        resource_id=str(user_id),
        db=audit_db,
    )
    assert ev1 is not None
    assert ev1.event_type == "auth_login_success"
    assert ev1.roles == ["Employee"]

    ev2 = await service.record_event(
        event_type=AuditEventType.AUTHORIZATION_DENIED,
        action="access_admin_panel",
        severity=AuditSeverity.HIGH,
        principal={"user_id": user_id, "email": "user1@enterprise.com", "roles": ["Employee"], "clearance_level": 1},
        resource_type="endpoint",
        resource_id="/api/v1/audit/events",
        authorization_result=AuthorizationResult.DENIED,
        db=audit_db,
    )
    assert ev2 is not None

    # Query all events
    filter_all = AuditQueryFilter(limit=10, offset=0)
    items, total = await service.query_events(filter_all, audit_db)
    assert total == 2
    assert len(items) == 2
    # Deterministic ordering: created_at DESC
    assert items[0].id == ev2.id
    assert items[1].id == ev1.id

    # Query filtered by severity
    filter_high = AuditQueryFilter(severity=AuditSeverity.HIGH)
    items_high, total_high = await service.query_events(filter_high, audit_db)
    assert total_high == 1
    assert items_high[0].event_type == "authorization_denied"


@pytest.mark.asyncio
async def test_tamper_evident_hash_chain_and_tamper_detection(audit_db):
    """Verifies that audit hash chains are correctly computed and modifications are detected."""
    service = AuditService()

    # Record two chained events
    e1 = await service.record_event(
        event_type=AuditEventType.DOCUMENT_CREATED,
        action="upload",
        resource_type="document",
        resource_id="doc-100",
        db=audit_db,
    )
    e2 = await service.record_event(
        event_type=AuditEventType.RAG_QUERY,
        action="query",
        resource_type="rag",
        raw_query="Security policy overview",
        db=audit_db,
    )

    assert e1.event_hash is not None
    assert e2.event_hash is not None
    assert e2.previous_event_hash == e1.event_hash

    # Validate intact chain
    is_valid, violations = service.verify_audit_log_chain([e1, e2])
    assert is_valid is True
    assert len(violations) == 0

    # Simulate unauthorized record tampering (e.g. attacker modifies action)
    tampered_e1 = AuditEvent(
        id=e1.id,
        created_at=e1.created_at,
        request_id=e1.request_id,
        event_type=e1.event_type,
        severity=e1.severity,
        user_id=e1.user_id,
        action="tampered_unauthorized_action",  # Modified field
        resource_type=e1.resource_type,
        resource_id=e1.resource_id,
        authorization_result=e1.authorization_result,
        query_fingerprint=e1.query_fingerprint,
        event_hash=e1.event_hash,
        previous_event_hash=e1.previous_event_hash,
        metadata_json=e1.metadata_json,
    )

    is_valid_tampered, tampered_violations = service.verify_audit_log_chain([tampered_e1, e2])
    assert is_valid_tampered is False
    assert len(tampered_violations) > 0
    assert "integrity failure" in tampered_violations[0]
