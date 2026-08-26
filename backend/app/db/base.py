"""
SQLAlchemy Declarative Base and shared model mixins.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy 2.0 ORM models.
    """
    pass


class TimestampMixin:
    """
    Mixin providing timezone-aware created_at timestamp.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """
    Mixin providing a UUID primary key.
    """
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
        nullable=False,
    )
