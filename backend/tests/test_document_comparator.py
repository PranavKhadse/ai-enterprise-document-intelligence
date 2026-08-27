"""
Unit tests for DocumentComparatorService.
Verifies full comparison orchestration: identical docs, additions, removals, modifications,
polarity reversals, numeric conflicts, divergence index calculations, and LLM explanation fallbacks.
"""
import pytest
from backend.app.schemas.comparison import (
    ConflictSeverity,
    DiffType,
    DocumentComparisonRequest,
    DocumentComparisonResponse,
)
from backend.app.services.document_comparator import DocumentComparatorService, document_comparator
from backend.app.services.llm_provider import MockLLMProvider


@pytest.mark.asyncio
async def test_comparator_identical_documents():
    """Verifies that identical documents yield 0.0 divergence and UNCHANGED diff types."""
    doc_text = """
# 1. Security
Multi-factor authentication is mandatory.

# 2. Storage
Backups are stored for 30 days.
"""
    req = DocumentComparisonRequest(
        text_a=doc_text,
        text_b=doc_text,
        title_a="Policy v1",
        title_b="Policy v1 Copy",
    )

    resp = await document_comparator.compare_documents(req)

    assert isinstance(resp, DocumentComparisonResponse)
    assert resp.statistics.divergence_index == 0.0
    assert resp.statistics.unchanged_clauses_count == 2
    assert resp.statistics.conflicting_clauses_count == 0
    assert len(resp.conflicts) == 0


@pytest.mark.asyncio
async def test_comparator_polarity_conflict():
    """Verifies that changing a mandatory policy to optional is classified as CONFLICT (HIGH severity)."""
    doc_a = """
# 1. Authentication
Multi-factor authentication is mandatory for all production systems.
"""
    doc_b = """
# 1. Authentication
Multi-factor authentication is optional and discretionary for all production systems.
"""
    req = DocumentComparisonRequest(
        text_a=doc_a,
        text_b=doc_b,
        title_a="Security v1.0",
        title_b="Security v2.0",
    )

    resp = await document_comparator.compare_documents(req)

    assert resp.statistics.conflicting_clauses_count == 1
    assert len(resp.conflicts) == 1
    assert resp.conflicts[0].diff_type == DiffType.CONFLICT
    assert resp.conflicts[0].conflict_severity == ConflictSeverity.HIGH
    assert resp.conflicts[0].conflict_verified is True


@pytest.mark.asyncio
async def test_comparator_duration_conflict():
    """Verifies that changed retention period (30 days vs 90 days) is classified as CONFLICT."""
    doc_a = """
# 1. Retention Policy
Snapshot backups are retained for 30 days.
"""
    doc_b = """
# 1. Retention Policy
Snapshot backups are retained for 90 days.
"""
    req = DocumentComparisonRequest(
        text_a=doc_a,
        text_b=doc_b,
        title_a="Storage v1",
        title_b="Storage v2",
    )

    resp = await document_comparator.compare_documents(req)

    assert resp.statistics.conflicting_clauses_count == 1
    assert resp.conflicts[0].diff_type == DiffType.CONFLICT
    assert any(d.entity_type == "duration" and d.is_divergent for d in resp.conflicts[0].entity_diffs)


@pytest.mark.asyncio
async def test_comparator_additions_and_removals():
    """Verifies that unmatched clauses are correctly classified as ADDED or REMOVED."""
    doc_a = """
# 1. Introduction
Welcome to company handbook.

# 2. Deprecated Section
This policy is obsolete.
"""
    doc_b = """
# 1. Introduction
Welcome to company handbook.

# 2. New Remote Work Policy
Remote employees receive a home stipend.
"""
    req = DocumentComparisonRequest(
        text_a=doc_a,
        text_b=doc_b,
        title_a="Handbook v1",
        title_b="Handbook v2",
    )

    resp = await document_comparator.compare_documents(req)

    assert resp.statistics.removed_clauses_count == 1
    assert resp.statistics.added_clauses_count == 1
    assert resp.statistics.unchanged_clauses_count == 1
    assert resp.statistics.divergence_index > 0.0


@pytest.mark.asyncio
async def test_comparator_llm_fallback_on_error():
    """Verifies that comparison completes gracefully using deterministic fallback if LLM times out."""
    mock_p = MockLLMProvider(mode="timeout")
    service = DocumentComparatorService(llm=mock_p)

    doc_a = "# 1. Policy\nEmployees must work 40 hours per week."
    doc_b = "# 1. Policy\nEmployees must work 35 hours per week."

    req = DocumentComparisonRequest(text_a=doc_a, text_b=doc_b)
    resp = await service.compare_documents(req)

    assert isinstance(resp, DocumentComparisonResponse)
    assert len(resp.aligned_clauses) == 1
    assert resp.aligned_clauses[0].diff_type in [DiffType.MODIFIED, DiffType.CONFLICT]
