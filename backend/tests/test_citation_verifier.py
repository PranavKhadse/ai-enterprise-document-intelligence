"""
Unit tests for CitationVerifierService.
Verifies citation extraction, range parsing, fabrication detection, out-of-bounds rejection,
and server-side provenance reconstruction from RAGContextItem.
"""
import uuid
import pytest
from backend.app.schemas.reranking import RAGContextItem
from backend.app.services.citation_verifier import CitationVerifierService, citation_verifier


def create_context_fixtures() -> list[RAGContextItem]:
    return [
        RAGContextItem(
            citation_id=1,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Security.pdf",
            page_number=4,
            section_path="Security > Auth",
            text="MFA is mandatory across all environments.",
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
            text="Backups are stored for 30 days.",
            relevance_score=0.88,
            is_table=False,
        ),
    ]


def test_citation_extraction_formats():
    """Verifies extraction and canonicalization of diverse bracketed citation formats."""
    verifier = CitationVerifierService()

    # Single
    assert verifier.extract_inline_citation_ids("Passage [1].") == [1]

    # Multiple comma-separated
    assert verifier.extract_inline_citation_ids("Passage [1, 2].") == [1, 2]
    assert verifier.extract_inline_citation_ids("Passage [1,2].") == [1, 2]

    # Multiple consecutive
    assert verifier.extract_inline_citation_ids("Passage [1][2].") == [1, 2]

    # Range format
    assert verifier.extract_inline_citation_ids("Passage [1-3].") == [1, 2, 3]


def test_citation_verifier_valid_reconstruction():
    """Verifies that valid citations are accurately mapped back to RAGContextItem provenance."""
    context = create_context_fixtures()
    answer_text = "MFA is required [1] and backups are retained for 30 days [2]."

    verified, warnings, invalid = citation_verifier.verify_and_reconstruct(
        answer_text=answer_text,
        proposed_citation_ids=[1, 2],
        context_items=context,
    )

    assert len(verified) == 2
    assert len(invalid) == 0
    assert verified[0].citation_id == 1
    assert verified[0].document_title == "Security.pdf"
    assert verified[0].page_number == 4
    assert verified[1].citation_id == 2
    assert verified[1].document_title == "Storage.pdf"


def test_citation_verifier_fabricated_citation_rejection():
    """Verifies that hallucinated/fabricated citations like [99] are rejected and flagged."""
    context = create_context_fixtures()
    answer_text = "The system mandates MFA [99]."

    verified, warnings, invalid = citation_verifier.verify_and_reconstruct(
        answer_text=answer_text,
        proposed_citation_ids=[99],
        context_items=context,
    )

    assert len(verified) == 0
    assert invalid == [99]
    assert any("Fabricated or out-of-bounds citation [99] rejected" in w for w in warnings)


def test_citation_verifier_mixed_valid_and_fabricated():
    """Verifies handling when answer contains both valid and fabricated citations."""
    context = create_context_fixtures()
    answer_text = "MFA is mandatory [1] and passwords must be 20 chars [5]."

    verified, warnings, invalid = citation_verifier.verify_and_reconstruct(
        answer_text=answer_text,
        proposed_citation_ids=[1, 5],
        context_items=context,
    )

    assert len(verified) == 1
    assert verified[0].citation_id == 1
    assert invalid == [5]
    assert len(warnings) == 1


def test_citation_verifier_deduplication():
    """Verifies that duplicate citations referencing the same item are deduplicated."""
    context = create_context_fixtures()
    answer_text = "MFA is mandatory [1]. As stated earlier, MFA is required [1][1]."

    verified, warnings, invalid = citation_verifier.verify_and_reconstruct(
        answer_text=answer_text,
        proposed_citation_ids=[1, 1],
        context_items=context,
    )

    assert len(verified) == 1
    assert verified[0].citation_id == 1
    assert len(invalid) == 0
