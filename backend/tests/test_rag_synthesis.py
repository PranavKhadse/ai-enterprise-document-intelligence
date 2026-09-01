"""
Unit tests for RAGSynthesisService.
Verifies grounded synthesis execution, early insufficient evidence guards,
degraded mode fallback on LLM failure, conflict detection, and telemetry diagnostics.
"""
import uuid
import pytest
from backend.app.schemas.rag import GroundingStatus, LLMAnswerProposal, LLMClaimProposal, RAGAnswer
from backend.app.schemas.reranking import RAGContextItem
from backend.app.services.llm_provider import MockLLMProvider
from backend.app.services.rag_synthesis import RAGSynthesisService, rag_synthesis_service


def create_context_fixtures() -> list[RAGContextItem]:
    return [
        RAGContextItem(
            citation_id=1,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Security.pdf",
            page_number=4,
            section_path="Auth > MFA",
            text="Multi-factor authentication is mandatory for all production systems starting v2.1.0.",
            relevance_score=0.95,
            is_table=False,
        ),
        RAGContextItem(
            citation_id=2,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Storage.pdf",
            page_number=10,
            section_path="Retention",
            text="Database backups are retained for 30 days in cold storage.",
            relevance_score=0.88,
            is_table=False,
        ),
    ]


@pytest.mark.asyncio
async def test_rag_synthesis_default_flow():
    """Verifies default grounded synthesis flow."""
    context = create_context_fixtures()
    answer = await rag_synthesis_service.synthesize(
        query="What is the MFA policy?",
        context_items=context,
    )

    assert isinstance(answer, RAGAnswer)
    assert answer.grounding_status in {GroundingStatus.FULLY_GROUNDED, GroundingStatus.PARTIALLY_GROUNDED}
    assert len(answer.citations) >= 1
    assert answer.insufficient_evidence is False
    assert answer.diagnostics.total_rag_latency_ms >= 0.0


@pytest.mark.asyncio
async def test_rag_synthesis_early_guard_empty_context():
    """Verifies that empty context triggers immediate structured refusal without calling LLM."""
    mock_p = MockLLMProvider(mode="failure")  # If LLM is called, it would throw
    service = RAGSynthesisService(provider=mock_p)

    answer = await service.synthesize(
        query="Any query with zero docs",
        context_items=[],
    )

    assert answer.insufficient_evidence is True
    assert answer.grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE
    assert "sufficient evidence" in answer.answer
    assert answer.diagnostics.evidence_count == 0


@pytest.mark.asyncio
async def test_rag_synthesis_degraded_fallback_on_llm_timeout():
    """Verifies graceful degraded fallback when LLM provider times out."""
    mock_p = MockLLMProvider(mode="timeout")
    service = RAGSynthesisService(provider=mock_p)
    context = create_context_fixtures()

    answer = await service.synthesize(
        query="What is the MFA policy?",
        context_items=context,
    )

    assert answer.diagnostics.degraded_mode is True
    assert len(answer.diagnostics.warnings) > 0
    assert "Based on retrieved document" in answer.answer
    assert len(answer.citations) >= 1


@pytest.mark.asyncio
async def test_rag_synthesis_conflict_detection():
    """Verifies detection of contradictory evidence across retrieved documents."""
    conflicting_context = [
        RAGContextItem(
            citation_id=1,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Policy_2023.pdf",
            page_number=1,
            section_path="Retention",
            text="Backup retention is 30 days.",
            relevance_score=0.95,
            is_table=False,
        ),
        RAGContextItem(
            citation_id=2,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Policy_2024.pdf",
            page_number=1,
            section_path="Retention",
            text="Backup retention is 90 days.",
            relevance_score=0.92,
            is_table=False,
        ),
    ]

    answer = await rag_synthesis_service.synthesize(
        query="What is the backup retention policy?",
        context_items=conflicting_context,
    )

    assert answer.conflicts_detected is True
    assert answer.conflict_details is not None
    assert "30" in answer.conflict_details and "90" in answer.conflict_details


@pytest.mark.asyncio
async def test_rag_synthesis_single_citation_grounded():
    """Verifies fully grounded status for a single citation [1]."""
    context = [create_context_fixtures()[0]]
    mock_p = MockLLMProvider(
        canned_proposal=LLMAnswerProposal(
            answer="Multi-factor authentication is mandatory for all production systems starting v2.1.0. [1]",
            claims=[
                LLMClaimProposal(
                    claim_text="Multi-factor authentication is mandatory for all production systems starting v2.1.0.",
                    citation_ids=[1],
                )
            ],
            citation_ids=[1],
            insufficient_evidence=False,
            conflicts_detected=False,
        )
    )
    service = RAGSynthesisService(provider=mock_p)
    answer = await service.synthesize(
        query="What is the MFA requirement?",
        context_items=context,
    )

    assert answer.grounding_status == GroundingStatus.FULLY_GROUNDED
    assert len(answer.citations) == 1
    assert answer.citations[0].citation_id == 1
    assert len(answer.claims) == 1
    assert answer.claims[0].citation_ids == [1]


@pytest.mark.asyncio
async def test_rag_synthesis_multiple_citations_grounded():
    """Verifies fully grounded status for multiple citations [1] and [2]."""
    context = create_context_fixtures()
    mock_p = MockLLMProvider(
        canned_proposal=LLMAnswerProposal(
            answer="MFA is mandatory starting v2.1.0 [1]. Database backups are retained for 30 days in cold storage [2].",
            claims=[
                LLMClaimProposal(
                    claim_text="MFA is mandatory starting v2.1.0",
                    citation_ids=[1],
                ),
                LLMClaimProposal(
                    claim_text="Database backups are retained for 30 days in cold storage",
                    citation_ids=[2],
                ),
            ],
            citation_ids=[1, 2],
            insufficient_evidence=False,
            conflicts_detected=False,
        )
    )
    service = RAGSynthesisService(provider=mock_p)
    answer = await service.synthesize(
        query="What are the security and retention policies?",
        context_items=context,
    )

    assert answer.grounding_status == GroundingStatus.FULLY_GROUNDED
    assert len(answer.citations) == 2
    assert [c.citation_id for c in answer.citations] == [1, 2]
    assert len(answer.claims) == 2


@pytest.mark.asyncio
async def test_rag_synthesis_fabricated_citation_rejected():
    """Verifies that fabricated citation [99] is rejected and downgrades grounding status."""
    context = create_context_fixtures()
    mock_p = MockLLMProvider(mode="fabricated_citation")
    service = RAGSynthesisService(provider=mock_p)
    answer = await service.synthesize(
        query="What is the MFA policy?",
        context_items=context,
    )

    assert answer.grounding_status in {GroundingStatus.PARTIALLY_GROUNDED, GroundingStatus.UNSUPPORTED}
    assert any("Fabricated or out-of-bounds citation [99]" in w for w in answer.warnings)


@pytest.mark.asyncio
async def test_rag_synthesis_unsupported_claim_no_citation():
    """Verifies that unsupported claim without citations is marked unsupported."""
    context = create_context_fixtures()
    mock_p = MockLLMProvider(
        canned_proposal=LLMAnswerProposal(
            answer="Passwords must be rotated every 7 days without exception.",
            claims=[
                LLMClaimProposal(
                    claim_text="Passwords must be rotated every 7 days without exception.",
                    citation_ids=[],
                )
            ],
            citation_ids=[],
            insufficient_evidence=False,
            conflicts_detected=False,
        )
    )
    service = RAGSynthesisService(provider=mock_p)
    answer = await service.synthesize(
        query="What is password rotation policy?",
        context_items=context,
    )

    assert answer.grounding_status == GroundingStatus.UNSUPPORTED
    assert len(answer.claims) == 1
    assert answer.claims[0].status.value == "unsupported"


@pytest.mark.asyncio
async def test_rag_synthesis_malformed_json_fallback():
    """Verifies graceful degraded fallback when LLM produces malformed JSON."""
    mock_p = MockLLMProvider(mode="malformed_json")
    service = RAGSynthesisService(provider=mock_p)
    context = create_context_fixtures()
    answer = await service.synthesize(
        query="What is the MFA policy?",
        context_items=context,
    )

    assert answer.diagnostics.degraded_mode is True
    assert len(answer.citations) >= 1
    assert "Based on retrieved document" in answer.answer
