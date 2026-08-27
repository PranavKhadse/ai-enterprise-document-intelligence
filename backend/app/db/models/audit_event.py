"""
AuditEvent ORM Model.
Provides tamper-evident, queryable, structured persistence for enterprise audit trails,
security anomalies, and compliance observability.
"""
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    AuditEvent entity representing immutable, append-only security and operational audit records.
    """
    __tablename__ = "audit_events"

    # Correlation & Identification
    request_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Correlation Request ID for distributed tracing",
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Standardized AuditEventType e.g. auth_login_success, rag_query",
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        default="info",
        nullable=False,
        index=True,
        comment="AuditSeverity level (info, warning, high, critical)",
    )

    # Authoritative Actor Identity (Phase 10 RBAC derived)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Database-authoritative user UUID",
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="User email address at time of event",
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
        comment="User department UUID at time of event",
    )
    roles: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Authoritative list of assigned role names",
    )
    clearance_level: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Authoritative effective clearance level (1-4)",
    )

    # Action & Target Resource
    action: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Action performed e.g. user_login, compare_documents",
    )
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Target resource category e.g. document, user, system",
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Identifier of affected resource",
    )
    authorization_result: Mapped[str] = mapped_column(
        String(32),
        default="allowed",
        nullable=False,
        index=True,
        comment="Authorization result (allowed, denied, unknown)",
    )

    # HTTP / Transport Context
    http_method: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="HTTP method e.g. GET, POST",
    )
    api_path: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Request URL path",
    )
    status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="HTTP response status code",
    )
    source_ip: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Client IP address",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Client User-Agent header",
    )

    # Privacy & Cryptographic Integrity
    query_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Deterministic SHA-256 fingerprint of search/RAG query",
    )
    event_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA-256 hash of canonical event data for tamper-evident chaining",
    )
    previous_event_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Event hash of preceding audit record",
    )

    # Sanitized Structured Metadata
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Sanitized, non-confidential telemetry payload",
    )

    __table_args__ = (
        Index("ix_audit_events_user_created", "user_id", "created_at"),
        Index("ix_audit_events_event_type_created", "event_type", "created_at"),
        Index("ix_audit_events_severity_created", "severity", "created_at"),
        Index("ix_audit_events_auth_result_created", "authorization_result", "created_at"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent(id={self.id}, type='{self.event_type}', severity='{self.severity}', "
            f"user='{self.email}', result='{self.authorization_result}')>"
        )
