"""
Phase 11 Audit Logging, Security Observability & Compliance Schemas.
Provides strongly typed Pydantic models for structured audit events, query filtering,
paginated listings, and administrative audit analytics.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditEventType(str, Enum):
    """Enumeration of standardized audit event categories."""
    AUTH_LOGIN_SUCCESS = "auth_login_success"
    AUTH_LOGIN_FAILURE = "auth_login_failure"
    AUTH_REGISTER = "auth_register"
    AUTH_LOGOUT = "auth_logout"
    AUTH_TOKEN_REVOKED = "auth_token_revoked"
    AUTH_ACCOUNT_DISABLED = "auth_account_disabled"
    AUTHORIZATION_DENIED = "authorization_denied"
    AUTHORIZATION_GRANTED = "authorization_granted"
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_READ = "document_read"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_COMPARED = "document_compared"
    RAG_QUERY = "rag_query"
    RAG_ACCESS_DENIED = "rag_access_denied"
    RBAC_FILTER_APPLIED = "rbac_filter_applied"
    ADMIN_ACTION = "admin_action"
    SECURITY_EVENT = "security_event"
    SYSTEM_EVENT = "system_event"


class AuditSeverity(str, Enum):
    """Audit event risk and urgency severity levels."""
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class AuthorizationResult(str, Enum):
    """Decision outcome of an authorization or access check."""
    ALLOWED = "allowed"
    DENIED = "denied"
    UNKNOWN = "unknown"


class AuditEventCreate(BaseModel):
    """Internal DTO used to create a new audit event."""
    model_config = ConfigDict(extra="ignore")

    request_id: Optional[str] = Field(default=None, max_length=64, description="Correlation Request ID")
    event_type: AuditEventType = Field(description="Standardized audit event type")
    severity: AuditSeverity = Field(default=AuditSeverity.INFO, description="Event severity classification")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Authoritative authenticated user ID")
    email: Optional[str] = Field(default=None, max_length=255, description="Authoritative user email")
    department_id: Optional[uuid.UUID] = Field(default=None, description="User department UUID")
    roles: List[str] = Field(default_factory=list, description="Authoritative user role names")
    clearance_level: Optional[int] = Field(default=None, ge=1, le=4, description="Authoritative clearance level (1-4)")
    action: str = Field(max_length=128, description="Action performed e.g. login, query, delete")
    resource_type: Optional[str] = Field(default=None, max_length=64, description="Resource classification e.g. document, user, config")
    resource_id: Optional[str] = Field(default=None, max_length=255, description="Unique identifier of affected resource")
    authorization_result: AuthorizationResult = Field(default=AuthorizationResult.ALLOWED, description="Outcome of authz check")
    http_method: Optional[str] = Field(default=None, max_length=16, description="HTTP request method e.g. GET, POST")
    api_path: Optional[str] = Field(default=None, max_length=512, description="Request path e.g. /api/v1/rag/query")
    status_code: Optional[int] = Field(default=None, ge=100, le=599, description="HTTP status code")
    source_ip: Optional[str] = Field(default=None, max_length=64, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, max_length=512, description="Client User-Agent")
    query_fingerprint: Optional[str] = Field(default=None, max_length=64, description="Deterministic SHA-256 fingerprint of query")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Sanitized, non-confidential event metadata")


class AuditEventResponse(BaseModel):
    """Public read model DTO for an audit event."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    request_id: Optional[str] = None
    event_type: str
    severity: str
    user_id: Optional[uuid.UUID] = None
    email: Optional[str] = None
    department_id: Optional[uuid.UUID] = None
    roles: List[str] = Field(default_factory=list)
    clearance_level: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    authorization_result: str
    http_method: Optional[str] = None
    api_path: Optional[str] = None
    status_code: Optional[int] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    query_fingerprint: Optional[str] = None
    event_hash: Optional[str] = None
    previous_event_hash: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class AuditEventListResponse(BaseModel):
    """Paginated collection response for audit events."""
    items: List[AuditEventResponse] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total matching records count")
    limit: int = Field(ge=1, le=100, description="Pagination size limit")
    offset: int = Field(ge=0, description="Pagination offset")


class AuditQueryFilter(BaseModel):
    """Structured parameters for querying and filtering audit logs."""
    model_config = ConfigDict(extra="forbid")

    event_type: Optional[AuditEventType] = None
    severity: Optional[AuditSeverity] = None
    user_id: Optional[uuid.UUID] = None
    request_id: Optional[str] = Field(default=None, max_length=64)
    resource_type: Optional[str] = Field(default=None, max_length=64)
    resource_id: Optional[str] = Field(default=None, max_length=255)
    authorization_result: Optional[AuthorizationResult] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("end_time")
    @classmethod
    def validate_time_window(cls, v: Optional[datetime], info) -> Optional[datetime]:
        start = info.data.get("start_time")
        if start and v and v < start:
            raise ValueError("end_time must be greater than or equal to start_time")
        return v


class AuditStatisticsResponse(BaseModel):
    """Aggregated security and compliance observability metrics."""
    total_events: int = Field(ge=0, description="Total recorded audit events in time window")
    events_by_type: Dict[str, int] = Field(default_factory=dict, description="Event breakdown by event_type")
    events_by_severity: Dict[str, int] = Field(default_factory=dict, description="Event breakdown by severity")
    authorization_denials: int = Field(ge=0, description="Total access/authorization denials")
    authentication_failures: int = Field(ge=0, description="Total failed authentication attempts")
    active_users_with_events: int = Field(ge=0, description="Count of distinct users with recorded activity")
    unique_resources_accessed: int = Field(ge=0, description="Count of distinct resources accessed")
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
