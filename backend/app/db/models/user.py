"""
User ORM model.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.department import Department
    from backend.app.db.models.role import Role
    from backend.app.db.models.query_log import QueryLog


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    User entity representing system actors.
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    # Relationships
    department: Mapped[Optional["Department"]] = relationship(
        "Department",
        back_populates="users",
        lazy="joined",
    )
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        lazy="selectin",
    )
    query_logs: Mapped[List["QueryLog"]] = relationship(
        "QueryLog",
        back_populates="user",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', is_active={self.is_active})>"
