"""
Pydantic schemas for Cross-Encoder Reranking, Context Compression, Evidence Selection,
and the frozen Phase 8 RAG Context Contract.
"""
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.retrieval import RetrievalDiagnostics, ScoredChunk


class RerankerConfig(BaseModel):
    """
    Configuration parameters for Cross-Encoder Reranker inference.
    """
    enabled: bool = Field(default=True, description="Whether reranking is active")
    model_name: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2", description="Hugging Face repo or local path")
    onnx_filename: str = Field(default="onnx/model.onnx", description="Relative ONNX model path inside repo")
    top_k: int = Field(default=10, description="Final number of top reranked chunks to return")
    candidate_window_size: int = Field(default=25, description="Number of Phase 6 candidates to slice for reranking")
    batch_size: int = Field(default=16, description="Inference batch size")
    max_length: int = Field(default=512, description="Maximum total sequence length for tokenization")
    query_max_tokens: int = Field(default=128, description="Maximum tokens reserved for the query sequence")
    timeout_seconds: float = Field(default=3.0, description="Inference execution timeout in seconds")

    model_config = ConfigDict(from_attributes=True)


class CompressionConfig(BaseModel):
    """
    Configuration parameters for deterministic context compression and evidence selection.
    """
    enabled: bool = Field(default=True, description="Whether context compression is enabled")
    target_tokens_per_chunk: int = Field(default=150, description="Target token budget per compressed chunk")
    max_context_tokens: int = Field(default=1500, description="Hard ceiling for total packed context tokens in Phase 8")
    preserve_tables: bool = Field(default=True, description="Whether to bypass compression on table structures")
    near_duplicate_threshold: float = Field(default=0.85, description="Token Jaccard similarity threshold for deduplication")
    max_chunks_per_section: int = Field(default=2, description="Maximum chunks allowed per (document_id, section_path)")

    model_config = ConfigDict(from_attributes=True)


class RerankedChunk(BaseModel):
    """
    Passage representation after Cross-Encoder reranking and context compression.
    Preserves full Phase 6 retrieval provenance while establishing raw reranking scores.
    """
    chunk_id: uuid.UUID = Field(..., description="DocumentChunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional DocumentVersion UUID")
    department_id: Optional[uuid.UUID] = Field(None, description="Optional Department UUID")
    content: str = Field(..., description="Original full context-enriched chunk passage text")
    compressed_content: Optional[str] = Field(None, description="Compressed verbatim passage text")
    page_number: Optional[int] = Field(None, description="Primary starting page number")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb path")
    is_table: bool = Field(default=False, description="True if chunk represents tabular data")

    # Phase 7 Scoring
    reranker_raw_score: float = Field(..., description="Raw cross-encoder logit output from the model")
    reranker_score: float = Field(..., description="Sigmoid normalized monotonic score [0.0, 1.0]")
    reranker_rank: int = Field(..., description="1-based rank position after cross-encoder reranking")
    rank_delta: int = Field(default=0, description="Phase 6 initial rank minus Phase 7 reranked rank")

    # Phase 6 Retained Metrics & Provenance
    initial_retrieval_score: float = Field(..., description="Phase 6 hybrid retrieval fusion score")
    initial_retrieval_rank: int = Field(..., description="1-based rank position from Phase 6")
    dense_score: Optional[float] = Field(None, description="Raw dense cosine similarity")
    sparse_score: Optional[float] = Field(None, description="Raw BM25 score")
    dense_rank: Optional[int] = Field(None, description="Dense rank position")
    sparse_rank: Optional[int] = Field(None, description="Sparse rank position")
    rrf_score: Optional[float] = Field(None, description="RRF score from Phase 6")
    retrieval_methods: List[str] = Field(default_factory=list, description="Methods that retrieved this chunk ('dense', 'bm25')")

    # Token Metrics
    original_token_count: int = Field(..., description="Token count of original content")
    compressed_token_count: int = Field(..., description="Token count of compressed content")
    compression_ratio: float = Field(..., description="Ratio of compressed tokens to original tokens")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")

    model_config = ConfigDict(from_attributes=True)


class RerankingDiagnostics(BaseModel):
    """
    Structured execution diagnostics, timing breakdowns, and token reduction metrics for Phase 7.
    """
    query: str = Field(..., description="Query text")
    reranker_model: str = Field(..., description="Model identifier used for reranking")
    reranker_latency_ms: float = Field(default=0.0, description="Cross-encoder inference latency in ms")
    compression_latency_ms: float = Field(default=0.0, description="Context compression execution time in ms")
    selection_latency_ms: float = Field(default=0.0, description="Diversity & evidence selection time in ms")
    total_phase7_latency_ms: float = Field(default=0.0, description="Total Phase 7 processing latency in ms")
    input_candidates_count: int = Field(default=0, description="Number of Phase 6 candidates passed in")
    candidate_window_size: int = Field(default=0, description="Number of candidates sliced for reranking")
    reranked_candidates_count: int = Field(default=0, description="Number of candidates evaluated by cross-encoder")
    final_evidence_count: int = Field(default=0, description="Final number of evidence chunks selected")
    total_original_tokens: int = Field(default=0, description="Sum of original token counts across selected chunks")
    total_compressed_tokens: int = Field(default=0, description="Sum of compressed tokens packed into context")
    overall_compression_ratio: float = Field(default=0.0, description="Aggregate token compression ratio")
    degraded_mode: bool = Field(default=False, description="True if fallback or degraded mode was triggered")
    warnings: List[str] = Field(default_factory=list, description="Warnings encountered during Phase 7 execution")
    phase6_diagnostics: Optional[RetrievalDiagnostics] = Field(None, description="Preserved Phase 6 retrieval diagnostics")

    model_config = ConfigDict(from_attributes=True)


class RAGContextItem(BaseModel):
    """
    Frozen Phase 8 RAG Context Contract.
    Minimal, stable, citation-ready evidence unit for downstream LLM synthesis.
    """
    citation_id: int = Field(..., description="1-based citation index: [1], [2], etc.")
    chunk_id: uuid.UUID = Field(..., description="DocumentChunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    document_title: Optional[str] = Field(None, description="Document title if available")
    page_number: Optional[int] = Field(None, description="Original source page number for citations")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb (e.g., Doc > H1 > H2)")
    text: str = Field(..., description="Verbatim (or compressed) passage text ready for prompt injection")
    relevance_score: float = Field(..., description="Normalized relevance score [0.0, 1.0]")
    is_table: bool = Field(default=False, description="True if evidence represents tabular data")

    model_config = ConfigDict(from_attributes=True)


class RerankedRetrievalResponse(BaseModel):
    """
    Complete response schema returned by the Phase 7 Reranking Pipeline.
    """
    results: List[RerankedChunk] = Field(default_factory=list, description="Reranked and compressed chunks")
    context_items: List[RAGContextItem] = Field(default_factory=list, description="Frozen Phase 8 RAG context items")
    diagnostics: RerankingDiagnostics = Field(..., description="Execution diagnostics and latency metrics")

    model_config = ConfigDict(from_attributes=True)
