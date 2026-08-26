"""
DocumentChunk ORM model.
"""
import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.document import Document
    from backend.app.db.models.document_version import DocumentVersion


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    DocumentChunk entity storing parsed, context-enriched passage units
    along with section breadcrumbs and page provenance.
    """
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
        comment="0-indexed sequence position of the chunk in the document",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Flexible JSON metadata: headers, tables, language, character offsets",
    )
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        index=True,
        nullable=True,
        comment="Original source page number for citations",
    )
    section_path: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Hierarchical breadcrumb path (e.g. Doc > H1 > H2)",
    )
    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of tokens in chunk",
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
        lazy="joined",
    )
    version: Mapped[Optional["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="chunks",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, doc_id={self.document_id}, index={self.chunk_index}, page={self.page_number})>"
