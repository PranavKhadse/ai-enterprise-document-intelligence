"""
Unit tests for Phase 8 RAG Schemas and DTOs.
Verifies Pydantic v2 validation, bounds enforcement, serialization, and default behaviors.
"""
import uuid
import pytest
from pydantic import ValidationError
from backend.app.schemas.rag import (
    Citation,
    ClaimStatus,
    ClaimVerification,
    GroundingStatus,
    LLMAnswerProposal,
    LLMClaimProposal,
    RAGAnswer,
    RAGDiagnostics,
    RAGQueryRequest,
)


def test_rag_query_request_validation():
    """Verifies bounds and validation on RAGQueryRequest."""
    # Valid request
    req = RAGQueryRequest(query="What is the password policy?")
    assert req.query == "What is the password policy?"
    assert req.temperature == 0.0
    assert req.enable_verification is True

    # Empty query should fail
    with pytest.raises(ValidationError):
        RAGQueryRequest(query="")

    # Temperature out of bounds should fail
    with pytest.raises(ValidationError):
        RAGQueryRequest(query="test", temperature=1.5)

    with pytest.raises(ValidationError):
        RAGQueryRequest(query="test", temperature=-0.1)


def test_citation_schema_structure():
    """Verifies Citation model attributes and types."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    citation = Citation(
        citation_id=1,
        chunk_id=chunk_id,
        document_id=doc_id,
        document_title="Security.pdf",
        page_number=3,
        section_path="Security > Auth",
        quoted_or_supported_text="MFA is mandatory.",
        relevance_score=0.95,
        is_table=False,
    )
    assert citation.citation_id == 1
    assert citation.chunk_id == chunk_id
    assert citation.document_id == doc_id
    assert citation.page_number == 3
    assert citation.relevance_score == 0.95


def test_claim_verification_schema():
    """Verifies ClaimVerification status enum and entity fields."""
    claim = ClaimVerification(
        claim_text="MFA is required starting v2.4.0.",
        citation_ids=[1, 2],
        status=ClaimStatus.SUPPORTED,
        entailment_score=0.88,
        unsupported_entities=[],
        explanation="Directly supported by citation [1].",
    )
    assert claim.status == ClaimStatus.SUPPORTED
    assert claim.entailment_score == 0.88
    assert claim.citation_ids == [1, 2]


def test_llm_answer_proposal_schema():
    """Verifies LLMAnswerProposal schema parsing."""
    prop = LLMAnswerProposal(
        answer="Passage details [1].",
        claims=[LLMClaimProposal(claim_text="Passage details", citation_ids=[1])],
        citation_ids=[1],
        insufficient_evidence=False,
        conflicts_detected=False,
    )
    assert prop.citation_ids == [1]
    assert len(prop.claims) == 1
    assert prop.claims[0].claim_text == "Passage details"


def test_rag_answer_full_contract():
    """Verifies complete RAGAnswer contract creation and serialization."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    answer = RAGAnswer(
        query="What is the retention period?",
        answer="Backups are retained for 30 days. [1]",
        grounding_status=GroundingStatus.FULLY_GROUNDED,
        citations=[
            Citation(
                citation_id=1,
                chunk_id=chunk_id,
                document_id=doc_id,
                document_title="Spec.pdf",
                page_number=12,
                section_path="Storage > Backups",
                quoted_or_supported_text="Database snapshots are retained for 30 days.",
                relevance_score=0.92,
                is_table=False,
            )
        ],
        claims=[
            ClaimVerification(
                claim_text="Backups are retained for 30 days.",
                citation_ids=[1],
                status=ClaimStatus.SUPPORTED,
                entailment_score=0.95,
                unsupported_entities=[],
                explanation="Verified against passage text.",
            )
        ],
        insufficient_evidence=False,
        conflicts_detected=False,
        warnings=[],
        diagnostics=RAGDiagnostics(
            query="What is the retention period?",
            provider="mock",
            model="mock-deterministic",
            llm_latency_ms=10.5,
            prompt_builder_latency_ms=1.2,
            citation_verifier_latency_ms=0.8,
            grounding_verifier_latency_ms=1.5,
            total_rag_latency_ms=14.0,
            prompt_tokens=150,
            completion_tokens=25,
            evidence_count=1,
            citation_count=1,
            total_claims_count=1,
            supported_claims_count=1,
            unsupported_claims_count=0,
            degraded_mode=False,
        ),
    )

    data = answer.model_dump()
    assert data["grounding_status"] == "fully_grounded"
    assert len(data["citations"]) == 1
    assert data["diagnostics"]["total_rag_latency_ms"] == 14.0
