"""
Unit tests for GroundingVerifierService.
Verifies claim extraction, entity/numeric safety guards, lexical support heuristics,
and GroundingStatus classification across adversarial cases.
"""
import uuid
import pytest
from backend.app.schemas.rag import ClaimStatus, GroundingStatus, LLMClaimProposal
from backend.app.schemas.reranking import RAGContextItem
from backend.app.services.grounding_verifier import GroundingVerifierService, grounding_verifier


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
            text="Database backups are retained for 30 days in cold storage with a 5% margin.",
            relevance_score=0.88,
            is_table=False,
        ),
        RAGContextItem(
            citation_id=3,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Finance.pdf",
            page_number=2,
            section_path="Budget",
            text="The project budget is capped at $100,000 according to Clause_4.2.",
            relevance_score=0.91,
            is_table=False,
        ),
    ]


def test_grounding_verifier_fully_grounded():
    """Verifies fully grounded answer when claims match evidence and citations."""
    context = create_context_fixtures()
    answer = "Multi-factor authentication is mandatory starting v2.1.0 [1]. Backups are retained for 30 days [2]."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.FULLY_GROUNDED
    assert len(claims) == 2
    assert claims[0].status == ClaimStatus.SUPPORTED
    assert claims[1].status == ClaimStatus.SUPPORTED


def test_grounding_verifier_hallucinated_number():
    """Verifies that changed numerical values (e.g. 30 -> 90) fail verification."""
    context = create_context_fixtures()
    # Model claims 90 days instead of 30 days
    answer = "Database backups are retained for 90 days in cold storage [2]."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.UNSUPPORTED
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.UNSUPPORTED
    assert "Number: 90" in claims[0].unsupported_entities


def test_grounding_verifier_changed_version():
    """Verifies that changed software version strings fail verification."""
    context = create_context_fixtures()
    # Model claims v2.2.0 instead of v2.1.0
    answer = "MFA is mandatory starting v2.2.0 [1]."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.UNSUPPORTED
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.UNSUPPORTED
    assert "Version: v2.2.0" in claims[0].unsupported_entities


def test_grounding_verifier_changed_currency():
    """Verifies that changed currency amounts fail verification."""
    context = create_context_fixtures()
    # Model claims $1,000,000 instead of $100,000
    answer = "The project budget is capped at $1,000,000 according to Clause_4.2 [3]."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.UNSUPPORTED
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.UNSUPPORTED
    assert any("Currency:" in e or "Number:" in e for e in claims[0].unsupported_entities)


def test_grounding_verifier_changed_percentage():
    """Verifies that changed percentage numbers fail verification."""
    context = create_context_fixtures()
    # Model claims 50% instead of 5%
    answer = "Backups are stored with a 50% margin [2]."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.UNSUPPORTED
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.UNSUPPORTED
    assert "Percentage: 50%" in claims[0].unsupported_entities


def test_grounding_verifier_unsupported_claim_no_citation():
    """Verifies that claim with no citations is marked unsupported."""
    context = create_context_fixtures()
    answer = "The system automatically rotates passwords weekly."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.UNSUPPORTED
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.UNSUPPORTED


def test_grounding_verifier_partially_grounded():
    """Verifies partially grounded classification when one claim is valid and one is unsupported."""
    context = create_context_fixtures()
    answer = "MFA is mandatory starting v2.1.0 [1]. All passwords expire in 3 days."

    status, claims, warnings = grounding_verifier.verify_grounding(answer, context)

    assert status == GroundingStatus.PARTIALLY_GROUNDED
    assert len(claims) == 2
    assert claims[0].status == ClaimStatus.SUPPORTED
    assert claims[1].status == ClaimStatus.UNSUPPORTED
