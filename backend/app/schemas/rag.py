"""
Pydantic schemas and Data Transfer Objects for Phase 8 RAG Synthesis,
Deterministic Citation Verification, Grounding Evaluation, and Structured Answers.
"""
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.reranking import RerankingDiagnostics
from backend.app.schemas.retrieval import RetrievalFilter


class GroundingStatus(str, Enum):
    """Factual grounding classification determined by deterministic verification."""
    FULLY_GROUNDED = "fully_grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REFUSED = "refused"


class ClaimStatus(str, Enum):
    """Verification status for an individual factual claim assertion."""
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RAGQueryRequest(BaseModel):
    """
    Client request model for grounded RAG query synthesis.
    """
    query: str = Field(..., min_length=1, max_length=2000, description="User search / question query")
    filter: Optional[RetrievalFilter] = Field(None, description="Optional metadata filters (document, department, version)")
    top_k: Optional[int] = Field(None, ge=1, le=50, description="Candidate chunks to retrieve")
    max_context_tokens: Optional[int] = Field(None, ge=100, le=4000, description="Override token budget")
    temperature: Optional[float] = Field(default=0.0, ge=0.0, le=1.0, description="Generation temperature (default 0.0 for deterministic grounding)")
    enable_verification: bool = Field(default=True, description="Whether to execute grounding and citation verification")

    model_config = ConfigDict(from_attributes=True)


class Citation(BaseModel):
    """
    Authoritative citation unit reconstructed server-side from Phase 7 RAGContextItem.
    The LLM proposes the citation index, but the backend populates and verifies all metadata.
    """
    citation_id: int = Field(..., description="1-based citation index matching [N]")
    chunk_id: uuid.UUID = Field(..., description="Source DocumentChunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    document_title: Optional[str] = Field(None, description="Document title if available")
    page_number: Optional[int] = Field(None, description="Source page number for citations")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb (e.g., Doc > H1 > H2)")
    quoted_or_supported_text: str = Field(..., description="Verbatim or compressed passage text supporting the citation")
    relevance_score: float = Field(..., description="Cross-encoder relevance score [0.0, 1.0]")
    is_table: bool = Field(default=False, description="True if evidence represents tabular data")

    model_config = ConfigDict(from_attributes=True)


class ClaimVerification(BaseModel):
    """
    Deterministic verification record for an individual extracted claim.
    """
    claim_text: str = Field(..., description="Extracted factual assertion text")
    citation_ids: List[int] = Field(default_factory=list, description="Associated citation IDs [N]")
    status: ClaimStatus = Field(..., description="Verification status of the claim")
    entailment_score: float = Field(..., ge=0.0, le=1.0, description="Deterministic lexical/entity overlap heuristic score [0.0, 1.0]")
    unsupported_entities: List[str] = Field(default_factory=list, description="Entities/numbers in claim not found in cited evidence")
    explanation: str = Field(..., description="Reasoning for the assigned status")

    model_config = ConfigDict(from_attributes=True)


class LLMClaimProposal(BaseModel):
    """
    Internal schema for a claim proposed by the LLM.
    Status and provenance are not trusted and will be verified by Python code.
    """
    claim_text: str = Field(..., description="Factual claim assertion")
    citation_ids: List[int] = Field(default_factory=list, description="Proposed citation IDs")

    model_config = ConfigDict(from_attributes=True)


class LLMAnswerProposal(BaseModel):
    """
    Internal structured output proposal from the LLM provider.
    The LLM proposes; Python deterministic verification is the sole authority.
    """
    answer: str = Field(..., description="Synthesized answer text with inline citation anchors [1], [2]")
    claims: List[LLMClaimProposal] = Field(default_factory=list, description="List of proposed factual claims")
    citation_ids: List[int] = Field(default_factory=list, description="List of all referenced citation IDs")
    insufficient_evidence: bool = Field(default=False, description="Whether LLM deemed evidence insufficient")
    conflicts_detected: bool = Field(default=False, description="Whether LLM detected contradictory policies/values")
    conflict_details: Optional[str] = Field(None, description="Details of conflicting evidence if observed")

    model_config = ConfigDict(from_attributes=True)


class RAGDiagnostics(BaseModel):
    """
    Telemetry, latency breakdown, and execution observability for Phase 8.
    """
    query: str = Field(..., description="User query text")
    provider: str = Field(..., description="LLM provider name")
    model: str = Field(..., description="Model identifier")
    llm_latency_ms: float = Field(default=0.0, description="LLM inference latency in ms")
    prompt_builder_latency_ms: float = Field(default=0.0, description="Prompt formatting latency in ms")
    citation_verifier_latency_ms: float = Field(default=0.0, description="Citation verification latency in ms")
    grounding_verifier_latency_ms: float = Field(default=0.0, description="Grounding verification latency in ms")
    conflict_detector_latency_ms: float = Field(default=0.0, description="Conflict detection latency in ms")
    total_rag_latency_ms: float = Field(default=0.0, description="Total Phase 8 latency in ms")
    prompt_tokens: int = Field(default=0, description="Token count in generated prompt")
    completion_tokens: int = Field(default=0, description="Token count in LLM completion")
    evidence_count: int = Field(default=0, description="Number of evidence items provided")
    citation_count: int = Field(default=0, description="Number of unique valid citations emitted")
    total_claims_count: int = Field(default=0, description="Total extracted claims")
    supported_claims_count: int = Field(default=0, description="Claims verified as supported")
    unsupported_claims_count: int = Field(default=0, description="Claims flagged as unsupported")
    degraded_mode: bool = Field(default=False, description="True if provider fallback occurred")
    warnings: List[str] = Field(default_factory=list, description="Operational warnings encountered")
    phase7_diagnostics: Optional[RerankingDiagnostics] = Field(None, description="Preserved Phase 7 diagnostics")

    model_config = ConfigDict(from_attributes=True)


class RAGAnswer(BaseModel):
    """
    Authoritative final response contract for Phase 8 Grounded RAG.
    Constructed and validated entirely by backend code.
    """
    query: str = Field(..., description="Original user query")
    answer: str = Field(..., description="Grounded synthetic answer with inline citations [1], [2]")
    grounding_status: GroundingStatus = Field(..., description="Overall factual grounding status")
    citations: List[Citation] = Field(default_factory=list, description="Verified citations mapped to evidence")
    claims: List[ClaimVerification] = Field(default_factory=list, description="Per-claim verification breakdown")
    insufficient_evidence: bool = Field(default=False, description="True if context was insufficient to answer")
    conflicts_detected: bool = Field(default=False, description="True if contradictory evidence was identified")
    conflict_details: Optional[str] = Field(None, description="Summary of conflicting evidence if present")
    warnings: List[str] = Field(default_factory=list, description="System warnings")
    diagnostics: RAGDiagnostics = Field(..., description="End-to-end execution telemetry")

    model_config = ConfigDict(from_attributes=True)
