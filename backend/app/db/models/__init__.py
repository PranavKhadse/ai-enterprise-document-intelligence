"""
SQLAlchemy models package.
Imports all models to ensure registration with Base.metadata.
"""
from backend.app.db.base import Base
from backend.app.db.models.department import Department
from backend.app.db.models.role import Role
from backend.app.db.models.user_role import UserRole
from backend.app.db.models.user import User
from backend.app.db.models.document import Document
from backend.app.db.models.document_version import DocumentVersion
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.db.models.query_log import QueryLog
from backend.app.db.models.evaluation import EvaluationResult
from backend.app.db.models.audit_event import AuditEvent

__all__ = [
    "Base",
    "Department",
    "Role",
    "UserRole",
    "User",
    "Document",
    "DocumentVersion",
    "DocumentChunk",
    "QueryLog",
    "EvaluationResult",
    "AuditEvent",
]
