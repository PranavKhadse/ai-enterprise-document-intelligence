"""
DocumentVersion ORM model.
"""
import uuid
from typing import TYPE_CHECKING, List
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.document import Document
    from backend.app.db.models.document_chunk import DocumentChunk


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    DocumentVersion entity tracking historical iterations, diffs, and versions of documents.
    """
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of this specific version",
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="versions",
        lazy="joined",
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, doc_id={self.document_id}, version='{self.version_number}')>"
