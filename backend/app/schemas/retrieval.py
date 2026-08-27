"""
Pydantic schemas for Hybrid Retrieval, Query Analysis, Rank Fusion, and Evaluation.
"""
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class QueryType(str, Enum):
    """Classification of query intent and structural composition."""
    EXACT_IDENTIFIER = "exact_identifier"
    KEYWORD_SEARCH = "keyword_search"
    SEMANTIC_QUESTION = "semantic_question"
    MIXED = "mixed"


class FusionStrategy(str, Enum):
    """Rank and score fusion strategies for combining dense and sparse candidates."""
    RRF = "rrf"
    WEIGHTED_SCORE = "weighted_score"
    DENSE_ONLY = "dense_only"
    SPARSE_ONLY = "sparse_only"


class RetrievalFilter(BaseModel):
    """
    Standardized filter model applied consistently to Qdrant and BM25.
    Supports pre-retrieval authorization constraints for department isolation and clearance levels.
    """
    document_id: Optional[uuid.UUID] = Field(None, description="Optional document UUID filter")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional version UUID filter")
    department_id: Optional[uuid.UUID] = Field(None, description="Optional department UUID filter")
    is_table: Optional[bool] = Field(None, description="Optional table chunk filter")
    allowed_department_ids: Optional[List[uuid.UUID]] = Field(None, description="List of permitted department UUIDs")
    max_clearance_level: Optional[int] = Field(None, ge=1, le=4, description="Maximum security clearance level permitted")
    allowed_roles: Optional[List[str]] = Field(None, description="List of permitted roles")
    allowed_document_ids: Optional[List[uuid.UUID]] = Field(None, description="Permitted document IDs")

    model_config = ConfigDict(from_attributes=True)


class ScoredChunk(BaseModel):
    """
    Unified passage representation returned from hybrid retrieval with score breakdowns.
    """
    chunk_id: uuid.UUID = Field(..., description="DocumentChunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional DocumentVersion UUID")
    department_id: Optional[uuid.UUID] = Field(None, description="Optional Department UUID")
    content: str = Field(..., description="Context-enriched chunk passage text")
    page_number: Optional[int] = Field(None, description="Primary starting page number")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb")
    final_score: float = Field(..., description="Final fused ranking score")
    dense_score: Optional[float] = Field(None, description="Raw cosine similarity score (0.0 to 1.0)")
    sparse_score: Optional[float] = Field(None, description="Raw BM25 score")
    dense_rank: Optional[int] = Field(None, description="1-based rank position in dense candidate pool")
    sparse_rank: Optional[int] = Field(None, description="1-based rank position in sparse candidate pool")
    rrf_score: Optional[float] = Field(None, description="Calculated Reciprocal Rank Fusion score")
    normalized_dense_score: Optional[float] = Field(None, description="Min-Max normalized dense score")
    normalized_sparse_score: Optional[float] = Field(None, description="Min-Max normalized sparse score")
    retrieval_methods: List[str] = Field(default_factory=list, description="Methods that retrieved this chunk ('dense', 'bm25')")
    explanation: str = Field(..., description="Human-readable explanation of why this chunk was selected")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provenance and element metadata")

    model_config = ConfigDict(from_attributes=True)


class RetrievalDiagnostics(BaseModel):
    """
    Structured execution observability and performance metrics for a retrieval query.
    """
    query: str = Field(..., description="User query text")
    query_type: str = Field(..., description="Detected query intent classification")
    dense_latency_ms: float = Field(default=0.0, description="Embedding + Qdrant search latency in ms")
    sparse_latency_ms: float = Field(default=0.0, description="BM25 search latency in ms")
    fusion_latency_ms: float = Field(default=0.0, description="Deduplication and fusion latency in ms")
    total_latency_ms: float = Field(default=0.0, description="Total retrieval pipeline execution time in ms")
    dense_candidates_count: int = Field(default=0, description="Number of candidates retrieved from Qdrant")
    sparse_candidates_count: int = Field(default=0, description="Number of candidates retrieved from BM25")
    merged_candidates_count: int = Field(default=0, description="Total unique candidates merged before truncation")
    fusion_strategy: str = Field(..., description="Fusion method applied")
    degraded_mode: bool = Field(default=False, description="True if one retrieval backend failed and fallback was used")
    warnings: List[str] = Field(default_factory=list, description="Operational warnings encountered during retrieval")

    model_config = ConfigDict(from_attributes=True)


class HybridRetrievalResponse(BaseModel):
    """
    Complete hybrid retrieval response containing ranked candidate chunks and diagnostics.
    """
    results: List[ScoredChunk] = Field(default_factory=list, description="Ranked list of top-K chunks")
    diagnostics: RetrievalDiagnostics = Field(..., description="Diagnostics and latency breakdown")

    model_config = ConfigDict(from_attributes=True)


class EvalSample(BaseModel):
    """
    Evaluation sample containing query and ground-truth relevant chunk IDs.
    """
    query: str = Field(..., description="Evaluation query")
    expected_chunk_ids: List[uuid.UUID] = Field(..., description="List of ground truth relevant chunk UUIDs")
    relevance_grades: Optional[Dict[str, float]] = Field(None, description="Optional graded relevance weights (0.0 to 1.0)")
    filter: Optional[RetrievalFilter] = Field(None, description="Optional filter constraint")

    model_config = ConfigDict(from_attributes=True)


class EvaluationReport(BaseModel):
    """
    Comprehensive retrieval performance report across standard IR metrics.
    """
    recall_at_k: float = Field(..., description="Recall@K (fraction of relevant items retrieved)")
    precision_at_k: float = Field(..., description="Precision@K (fraction of retrieved items that are relevant)")
    hit_rate_at_k: float = Field(..., description="Hit Rate@K (1.0 if at least one relevant item in top K, else 0.0)")
    mrr: float = Field(..., description="Mean Reciprocal Rank across queries")
    ndcg_at_k: float = Field(..., description="Normalized Discounted Cumulative Gain at K")
    total_queries: int = Field(..., description="Number of queries evaluated")
    k: int = Field(..., description="Cutoff rank K")
    strategy: str = Field(..., description="Evaluated fusion strategy or retrieval method")

    model_config = ConfigDict(from_attributes=True)
