"""
Document ORM model.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.department import Department
    from backend.app.db.models.document_version import DocumentVersion
    from backend.app.db.models.document_chunk import DocumentChunk


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Document entity representing an ingested enterprise document.
    """
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    file_hash: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="SHA-256 hash of original file content for deduplication",
    )
    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Extension/MIME type: pdf, docx, md, txt",
    )
    total_pages: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    current_version: Mapped[str] = mapped_column(
        String(30),
        default="1.0.0",
        nullable=False,
    )

    # Relationships
    department: Mapped[Optional["Department"]] = relationship(
        "Department",
        back_populates="documents",
        lazy="joined",
    )
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.created_at.desc()",
        lazy="selectin",
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index.asc()",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title='{self.title}', version='{self.current_version}')>"
