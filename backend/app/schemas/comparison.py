"""
Phase 9 Document Comparison, Semantic Clause Alignment & Conflict Intelligence Schemas.
Defines strongly typed Pydantic models for clause diffing, entity variances, and comparison responses.
"""
from enum import Enum
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiffType(str, Enum):
    """Classification of semantic difference between document clauses."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


class ConflictSeverity(str, Enum):
    """Severity classification of detected policy contradictions."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EntityType(str, Enum):
    """Categorization of extracted enterprise entities and metrics."""
    NUMBER = "number"
    DURATION = "duration"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    DATE = "date"
    VERSION = "version"
    IDENTIFIER = "identifier"
    RFC = "rfc"
    ISO = "iso"
    CLAUSE_REFERENCE = "clause_reference"


class EntityDiffItem(BaseModel):
    """Represents a specific metric or entity variance between two paired clauses."""
    model_config = ConfigDict(frozen=True)

    entity_type: str = Field(description="Category of entity: duration, currency, version, etc.")
    value_a: Optional[str] = Field(default=None, description="Raw entity value in Document A")
    value_b: Optional[str] = Field(default=None, description="Raw entity value in Document B")
    normalized_value_a: Optional[str] = Field(default=None, description="Standardized representation in A")
    normalized_value_b: Optional[str] = Field(default=None, description="Standardized representation in B")
    is_divergent: bool = Field(default=False, description="True if values differ materially")


class AlignedClause(BaseModel):
    """Represents an aligned pair of clauses (or single added/removed clause) with difference details."""
    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(description="Deterministic unique ID for this clause alignment")
    section_path_a: Optional[str] = Field(default=None, description="Breadcrumb path in Document A")
    section_path_b: Optional[str] = Field(default=None, description="Breadcrumb path in Document B")
    text_a: Optional[str] = Field(default=None, description="Original text in Document A")
    text_b: Optional[str] = Field(default=None, description="Original text in Document B")
    page_a: Optional[int] = Field(default=None, description="Page number in Document A if available")
    page_b: Optional[int] = Field(default=None, description="Page number in Document B if available")
    diff_type: DiffType = Field(description="Semantic diff classification")
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Content similarity score")
    conflict_severity: Optional[ConflictSeverity] = Field(default=None, description="Severity if conflict detected")
    change_summary: Optional[str] = Field(default=None, description="Concise explanation of the change")
    entity_diffs: List[EntityDiffItem] = Field(default_factory=list, description="Extracted entity/metric differences")
    heading_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Heading match score")
    lexical_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Lexical Jaccard score")
    semantic_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Semantic embedding similarity score")
    alignment_method: Optional[str] = Field(default=None, description="structural, semantic, or unmatched")
    conflict_verified: bool = Field(default=False, description="True if verified deterministically by Python")


class ComparisonStatistics(BaseModel):
    """Aggregate numerical statistics for document version comparison."""
    model_config = ConfigDict(frozen=True)

    total_clauses_a: int = Field(ge=0, description="Total clauses extracted from Document A")
    total_clauses_b: int = Field(ge=0, description="Total clauses extracted from Document B")
    added_clauses_count: int = Field(ge=0, description="Count of newly added clauses in B")
    removed_clauses_count: int = Field(ge=0, description="Count of removed clauses from A")
    modified_clauses_count: int = Field(ge=0, description="Count of modified clauses")
    conflicting_clauses_count: int = Field(ge=0, description="Count of contradictory policy clauses")
    unchanged_clauses_count: int = Field(ge=0, description="Count of identical/unchanged clauses")
    divergence_index: float = Field(
        ge=0.0,
        le=1.0,
        description="Normalized divergence index (0.0 = identical, 1.0 = completely disjoint)",
    )


class ComparisonDiagnostics(BaseModel):
    """Detailed latency and execution diagnostics for comparison operation."""
    model_config = ConfigDict(frozen=True)

    extraction_latency_ms: float = Field(default=0.0, ge=0.0)
    alignment_latency_ms: float = 0.0
    entity_diff_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    clauses_a: int = 0
    clauses_b: int = 0
    aligned_pairs: int = 0
    unmatched_a: int = 0
    unmatched_b: int = 0
    llm_used: bool = False
    llm_fallback_used: bool = False
    warnings: List[str] = Field(default_factory=list)


class DocumentComparisonRequest(BaseModel):
    """Request payload for comparing two documents or ad-hoc texts."""
    model_config = ConfigDict(frozen=True)

    document_a_id: Optional[uuid.UUID] = Field(default=None, description="UUID of Document A in DB")
    document_b_id: Optional[uuid.UUID] = Field(default=None, description="UUID of Document B in DB")
    text_a: Optional[str] = Field(default=None, description="Ad-hoc raw text/markdown for Document A")
    text_b: Optional[str] = Field(default=None, description="Ad-hoc raw text/markdown for Document B")
    title_a: Optional[str] = Field(default=None, description="Optional title for Document A")
    title_b: Optional[str] = Field(default=None, description="Optional title for Document B")
    similarity_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score to align clauses (default 0.65)",
    )
    detect_conflicts_only: bool = Field(
        default=False,
        description="If True, filters aligned_clauses to return only conflicting/divergent items",
    )

    @model_validator(mode="after")
    def validate_document_sources(self) -> "DocumentComparisonRequest":
        """Ensures that both sides (A and B) have a valid source provided."""
        has_a = self.document_a_id is not None or (self.text_a is not None and self.text_a.strip() != "")
        has_b = self.document_b_id is not None or (self.text_b is not None and self.text_b.strip() != "")

        if not has_a or not has_b:
            raise ValueError(
                "Both Document A and Document B must have either a valid database ID (document_a_id/document_b_id) "
                "or non-empty raw text (text_a/text_b)."
            )
        return self


class DocumentComparisonResponse(BaseModel):
    """Complete response payload for document version comparison and conflict analysis."""
    model_config = ConfigDict(frozen=True)

    document_a_id: Optional[uuid.UUID] = Field(default=None)
    document_b_id: Optional[uuid.UUID] = Field(default=None)
    title_a: str = Field(description="Display title for Document A")
    title_b: str = Field(description="Display title for Document B")
    statistics: ComparisonStatistics = Field(description="Numerical diff statistics and divergence index")
    aligned_clauses: List[AlignedClause] = Field(description="All aligned clause comparisons")
    conflicts: List[AlignedClause] = Field(description="Verified high and medium severity conflicts")
    executive_summary: str = Field(description="Executive overview of differences and policy changes")
    diagnostics: ComparisonDiagnostics = Field(description="Telemetry and performance breakdown")
