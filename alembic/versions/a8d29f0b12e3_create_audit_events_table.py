"""Create audit_events table

Revision ID: a8d29f0b12e3
Revises: 6033bc07406f
Create Date: 2026-08-29 10:50:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8d29f0b12e3"
down_revision: Union[str, None] = "6033bc07406f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True, comment="Correlation Request ID for distributed tracing"),
        sa.Column("event_type", sa.String(length=64), nullable=False, comment="Standardized AuditEventType e.g. auth_login_success, rag_query"),
        sa.Column("severity", sa.String(length=32), server_default="info", nullable=False, comment="AuditSeverity level (info, warning, high, critical)"),
        sa.Column("user_id", sa.Uuid(), nullable=True, comment="Database-authoritative user UUID"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="User email address at time of event"),
        sa.Column("department_id", sa.Uuid(), nullable=True, comment="User department UUID at time of event"),
        sa.Column("roles", sa.JSON(), server_default="[]", nullable=False, comment="Authoritative list of assigned role names"),
        sa.Column("clearance_level", sa.Integer(), nullable=True, comment="Authoritative effective clearance level (1-4)"),
        sa.Column("action", sa.String(length=128), nullable=False, comment="Action performed e.g. user_login, compare_documents"),
        sa.Column("resource_type", sa.String(length=64), nullable=True, comment="Target resource category e.g. document, user, system"),
        sa.Column("resource_id", sa.String(length=255), nullable=True, comment="Identifier of affected resource"),
        sa.Column("authorization_result", sa.String(length=32), server_default="allowed", nullable=False, comment="Authorization result (allowed, denied, unknown)"),
        sa.Column("http_method", sa.String(length=16), nullable=True, comment="HTTP method e.g. GET, POST"),
        sa.Column("api_path", sa.String(length=512), nullable=True, comment="Request URL path"),
        sa.Column("status_code", sa.Integer(), nullable=True, comment="HTTP response status code"),
        sa.Column("source_ip", sa.String(length=64), nullable=True, comment="Client IP address"),
        sa.Column("user_agent", sa.String(length=512), nullable=True, comment="Client User-Agent header"),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=True, comment="Deterministic SHA-256 fingerprint of search/RAG query"),
        sa.Column("event_hash", sa.String(length=64), nullable=True, comment="SHA-256 hash of canonical event data for tamper-evident chaining"),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True, comment="Event hash of preceding audit record"),
        sa.Column("metadata_json", sa.JSON(), server_default="{}", nullable=False, comment="Sanitized, non-confidential telemetry payload"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_id"), "audit_events", ["id"], unique=False)
    op.create_index(op.f("ix_audit_events_request_id"), "audit_events", ["request_id"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_events_severity"), "audit_events", ["severity"], unique=False)
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_audit_events_resource_type"), "audit_events", ["resource_type"], unique=False)
    op.create_index(op.f("ix_audit_events_resource_id"), "audit_events", ["resource_id"], unique=False)
    op.create_index(op.f("ix_audit_events_authorization_result"), "audit_events", ["authorization_result"], unique=False)
    op.create_index(op.f("ix_audit_events_query_fingerprint"), "audit_events", ["query_fingerprint"], unique=False)
    op.create_index(op.f("ix_audit_events_event_hash"), "audit_events", ["event_hash"], unique=False)
    op.create_index("ix_audit_events_user_created", "audit_events", ["user_id", "created_at"], unique=False)
    op.create_index("ix_audit_events_event_type_created", "audit_events", ["event_type", "created_at"], unique=False)
    op.create_index("ix_audit_events_severity_created", "audit_events", ["severity", "created_at"], unique=False)
    op.create_index("ix_audit_events_auth_result_created", "audit_events", ["authorization_result", "created_at"], unique=False)
    op.create_index("ix_audit_events_resource", "audit_events", ["resource_type", "resource_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_events_resource", table_name="audit_events")
    op.drop_index("ix_audit_events_auth_result_created", table_name="audit_events")
    op.drop_index("ix_audit_events_severity_created", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type_created", table_name="audit_events")
    op.drop_index("ix_audit_events_user_created", table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_hash"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_query_fingerprint"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_authorization_result"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_resource_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_resource_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_severity"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_request_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_id"), table_name="audit_events")
    op.drop_table("audit_events")
