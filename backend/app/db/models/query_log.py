"""
QueryLog ORM model.
"""
import uuid
from typing import TYPE_CHECKING, Any, List, Optional
from sqlalchemy import Float, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.user import User
    from backend.app.db.models.evaluation import EvaluationResult


class QueryLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    QueryLog entity tracking incoming user queries, latency, token costs,
    and retrieved chunk provenance for auditing and observability.
    """
    __tablename__ = "query_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    rewritten_query: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    retrieved_chunk_ids: Mapped[List[Any]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Array of chunk UUIDs retrieved during the query",
    )
    llm_response: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Total end-to-end execution time in milliseconds",
    )
    prompt_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    completion_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Calculated monetary cost based on model pricing",
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="query_logs",
        lazy="joined",
    )
    evaluations: Mapped[List["EvaluationResult"]] = relationship(
        "EvaluationResult",
        back_populates="query_log",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<QueryLog(id={self.id}, user_id={self.user_id}, latency_ms={self.latency_ms})>"
