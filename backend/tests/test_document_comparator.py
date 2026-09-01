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


@pytest.mark.asyncio
async def test_comparator_load_from_document_chunks():
    """Verifies that DocumentComparatorService queries chunks by document ID and chunk_index."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock
    from backend.app.db.models.document import Document
    from backend.app.db.models.document_chunk import DocumentChunk

    doc_id = uuid.uuid4()
    mock_doc = Document(
        id=doc_id,
        title="Security Guidelines",
        file_path="dummy.pdf",
        file_type="pdf",
    )
    chunk1 = DocumentChunk(
        document_id=doc_id,
        chunk_index=0,
        content="# 1. Passwords\nPasswords must be at least 12 characters.",
    )
    chunk2 = DocumentChunk(
        document_id=doc_id,
        chunk_index=1,
        content="# 2. MFA\nMulti-factor authentication is mandatory.",
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_doc

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [chunk1, chunk2]
    mock_db.execute.return_value = mock_result

    warnings = []
    service = DocumentComparatorService(llm=MockLLMProvider())
    text, title = await service._load_document_text(doc_id, mock_db, warnings, "Doc A")

    assert title == "Security Guidelines"
    assert "Passwords must be at least 12 characters." in text
    assert "Multi-factor authentication is mandatory." in text
    assert "%PDF-" not in text


@pytest.mark.asyncio
async def test_comparator_pdf_fallback_when_no_chunks(tmp_path):
    """Verifies that PDFParserService.parse_file is used when no chunks exist, preventing raw PDF byte leaks."""
    import uuid
    import fitz
    from unittest.mock import AsyncMock, MagicMock
    from backend.app.db.models.document import Document

    # Create a real test PDF with clean text
    pdf_path = str(tmp_path / "test_policy.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "1. Incident Response\nIncidents must be reported within 30 minutes.", fontsize=12)
    doc.save(pdf_path)
    doc.close()

    doc_id = uuid.uuid4()
    mock_doc = Document(
        id=doc_id,
        title="Incident Policy",
        file_path=pdf_path,
        file_type="pdf",
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_doc

    # Return empty chunks to trigger PDF parsing fallback
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    warnings = []
    service = DocumentComparatorService(llm=MockLLMProvider())
    text, title = await service._load_document_text(doc_id, mock_db, warnings, "Doc A")

    assert title == "Incident Policy"
    assert "Incidents must be reported within 30 minutes." in text
    # Verify raw PDF binary internals are NEVER present
    assert "%PDF-" not in text
    assert "endobj" not in text
    assert "/Type /Page" not in text


@pytest.mark.asyncio
async def test_comparator_text_file_fallback(tmp_path):
    """Verifies that non-PDF text/markdown files are read correctly when no chunks exist."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock
    from backend.app.db.models.document import Document

    txt_path = str(tmp_path / "policy.md")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("# 1. Data Retention\nRetain logs for 365 days.")

    doc_id = uuid.uuid4()
    mock_doc = Document(
        id=doc_id,
        title="Retention Policy",
        file_path=txt_path,
        file_type="markdown",
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_doc

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    warnings = []
    service = DocumentComparatorService(llm=MockLLMProvider())
    text, title = await service._load_document_text(doc_id, mock_db, warnings, "Doc A")

    assert title == "Retention Policy"
    assert "Retain logs for 365 days." in text


def test_comparator_divergence_index_battery():
    """Verifies divergence index mathematical properties: 0.0 for identical, weights, and clamping."""
    service = DocumentComparatorService(llm=MockLLMProvider())

    # 1. Identical documents -> 0.0
    assert service.calculate_divergence_index(10, 10, 0, 0, 0, 0) == 0.0

    # 2. Only additions -> 0.75 * 10 / 10 = 0.75
    assert service.calculate_divergence_index(0, 10, 10, 0, 0, 0) == 0.75

    # 3. Only removals -> 0.75 * 10 / 10 = 0.75
    assert service.calculate_divergence_index(10, 0, 0, 10, 0, 0) == 0.75

    # 4. Only modifications -> 0.5 * 10 / 10 = 0.50
    assert service.calculate_divergence_index(10, 10, 0, 0, 10, 0) == 0.50

    # 5. Only conflicts -> 1.0 * 10 / 10 = 1.0
    assert service.calculate_divergence_index(10, 10, 0, 0, 0, 10) == 1.0

    # 6. Mixed changes
    assert service.calculate_divergence_index(10, 10, 2, 2, 2, 2) == 0.60

    # 7. Clamping check: raw > 1.0 is clamped to 1.0
    assert service.calculate_divergence_index(5, 5, 5, 5, 5, 5) == 1.0

