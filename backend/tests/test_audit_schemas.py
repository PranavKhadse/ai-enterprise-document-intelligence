"""
Unit tests for Phase 11 Audit schemas and DTOs.
Verifies enum definitions, payload validation, pagination constraints, and time window validation.
"""
from datetime import datetime, timezone
import uuid
import pytest
from pydantic import ValidationError
from backend.app.schemas.audit import (
    AuditEventCreate,
    AuditEventListResponse,
    AuditEventResponse,
    AuditEventType,
    AuditQueryFilter,
    AuditSeverity,
    AuditStatisticsResponse,
    AuthorizationResult,
)


def test_audit_enum_definitions():
    """Verifies all required event types and severity levels exist and match string representations."""
    assert AuditEventType.AUTH_LOGIN_SUCCESS == "auth_login_success"
    assert AuditEventType.AUTH_LOGIN_FAILURE == "auth_login_failure"
    assert AuditEventType.AUTH_REGISTER == "auth_register"
    assert AuditEventType.AUTH_TOKEN_REVOKED == "auth_token_revoked"
    assert AuditEventType.AUTH_ACCOUNT_DISABLED == "auth_account_disabled"
    assert AuditEventType.AUTHORIZATION_DENIED == "authorization_denied"
    assert AuditEventType.DOCUMENT_CREATED == "document_created"
    assert AuditEventType.DOCUMENT_READ == "document_read"
    assert AuditEventType.DOCUMENT_COMPARED == "document_compared"
    assert AuditEventType.RAG_QUERY == "rag_query"
    assert AuditEventType.SECURITY_EVENT == "security_event"
    assert AuditEventType.SYSTEM_EVENT == "system_event"

    assert AuditSeverity.INFO == "info"
    assert AuditSeverity.WARNING == "warning"
    assert AuditSeverity.HIGH == "high"
    assert AuditSeverity.CRITICAL == "critical"

    assert AuthorizationResult.ALLOWED == "allowed"
    assert AuthorizationResult.DENIED == "denied"


def test_audit_event_create_validation():
    """Verifies valid instantiation of AuditEventCreate with defaults."""
    dto = AuditEventCreate(
        event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
        action="user_login",
        user_id=uuid.uuid4(),
        email="test@enterprise.com",
        roles=["Employee"],
        clearance_level=1,
    )
    assert dto.event_type == AuditEventType.AUTH_LOGIN_SUCCESS
    assert dto.severity == AuditSeverity.INFO
    assert dto.authorization_result == AuthorizationResult.ALLOWED
    assert dto.roles == ["Employee"]
    assert dto.clearance_level == 1


def test_audit_query_filter_pagination_constraints():
    """Verifies limit bounds [1, 100] and offset >= 0."""
    # Valid filter
    qf = AuditQueryFilter(limit=50, offset=10)
    assert qf.limit == 50
    assert qf.offset == 10

    # Upper limit bound violation (max 100)
    with pytest.raises(ValidationError):
        AuditQueryFilter(limit=150)

    # Lower limit bound violation (min 1)
    with pytest.raises(ValidationError):
        AuditQueryFilter(limit=0)

    # Negative offset violation
    with pytest.raises(ValidationError):
        AuditQueryFilter(offset=-1)


def test_audit_query_filter_time_window_validation():
    """Verifies end_time cannot be earlier than start_time."""
    now = datetime.now(timezone.utc)
    earlier = datetime(2025, 1, 1, tzinfo=timezone.utc)

    # Valid window
    qf = AuditQueryFilter(start_time=earlier, end_time=now)
    assert qf.start_time == earlier
    assert qf.end_time == now

    # Invalid inverted window
    with pytest.raises(ValidationError) as exc:
        AuditQueryFilter(start_time=now, end_time=earlier)
    assert "end_time must be greater than or equal to start_time" in str(exc.value)


def test_audit_statistics_response_structure():
    """Verifies structure and aggregation fields of AuditStatisticsResponse."""
    stats = AuditStatisticsResponse(
        total_events=42,
        events_by_type={"auth_login_success": 30, "auth_login_failure": 12},
        events_by_severity={"info": 30, "warning": 12},
        authorization_denials=3,
        authentication_failures=12,
        active_users_with_events=5,
        unique_resources_accessed=8,
    )
    assert stats.total_events == 42
    assert stats.events_by_type["auth_login_success"] == 30
    assert stats.events_by_severity["warning"] == 12
    assert stats.authentication_failures == 12
