"""
Database package exposing Base, session manager, and models.
"""
from backend.app.db.base import Base
from backend.app.db.session import engine, AsyncSessionLocal, get_db
from backend.app.db.models import (
    Department,
    Role,
    UserRole,
    User,
    Document,
    DocumentVersion,
    DocumentChunk,
    QueryLog,
    EvaluationResult,
)

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "Department",
    "Role",
    "UserRole",
    "User",
    "Document",
    "DocumentVersion",
    "DocumentChunk",
    "QueryLog",
    "EvaluationResult",
]
