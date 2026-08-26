"""
Unit tests for EvidenceSelector.
Verifies token budget ceiling enforcement, near-duplicate suppression,
section density limits, and Phase 8 RAGContextItem generation.
"""
import uuid
from typing import Optional
import pytest
from backend.app.schemas.reranking import CompressionConfig, RAGContextItem, RerankedChunk
from backend.app.services.evidence_selector import EvidenceSelector


def create_reranked_candidate(
    content: str,
    reranker_score: float,
    doc_id: Optional[uuid.UUID] = None,
    section_path: str = "Doc > Section",
    token_count: Optional[int] = None,
    is_table: bool = False,
) -> RerankedChunk:
    d_id = doc_id or uuid.uuid4()
    tokens = token_count or len(content.split())
    return RerankedChunk(
        chunk_id=uuid.uuid4(),
        document_id=d_id,
        content=content,
        compressed_content=content,
        section_path=section_path,
        reranker_raw_score=reranker_score * 5.0,
        reranker_score=reranker_score,
        reranker_rank=1,
        initial_retrieval_score=0.8,
        initial_retrieval_rank=1,
        original_token_count=tokens,
        compressed_token_count=tokens,
        compression_ratio=1.0,
        is_table=is_table,
    )


def test_evidence_selector_hard_token_ceiling():
    """
    Verifies that evidence selector respects the max_context_tokens ceiling.
    """
    c1 = create_reranked_candidate("Text chunk 1 " * 12, reranker_score=0.9, token_count=60)
    c2 = create_reranked_candidate("Text chunk 2 " * 12, reranker_score=0.8, token_count=60)
    c3 = create_reranked_candidate("Text chunk 3 " * 12, reranker_score=0.7, token_count=60)

    selector = EvidenceSelector()
    selected_chunks, context_items = selector.select_evidence(
        chunks=[c1, c2, c3],
        max_context_tokens=100,
    )

    assert len(selected_chunks) == 1
    assert selected_chunks[0].chunk_id == c1.chunk_id
    assert len(context_items) == 1
    assert context_items[0].citation_id == 1


def test_evidence_selector_near_duplicate_suppression():
    """
    Verifies that near-duplicate passages (Jaccard similarity >= 0.85) are suppressed.
    """
    text_orig = "Eligible full-time employees are entitled to 26 weeks of paid maternity leave."
    text_near_dup = "Eligible full time employees are entitled to 26 weeks of paid maternity leave."

    c1 = create_reranked_candidate(text_orig, reranker_score=0.95)
    c2 = create_reranked_candidate(text_near_dup, reranker_score=0.85)

    selector = EvidenceSelector(config=CompressionConfig(near_duplicate_threshold=0.85))
    selected_chunks, context_items = selector.select_evidence(chunks=[c1, c2])

    assert len(selected_chunks) == 1
    assert selected_chunks[0].chunk_id == c1.chunk_id


def test_evidence_selector_section_density_limit():
    """
    Verifies that a maximum of 2 chunks from the same document/section are accepted.
    """
    shared_doc = uuid.uuid4()
    shared_sec = "Policy > Leave"

    c1 = create_reranked_candidate("Section Leave Part 1", reranker_score=0.95, doc_id=shared_doc, section_path=shared_sec)
    c2 = create_reranked_candidate("Section Leave Part 2", reranker_score=0.90, doc_id=shared_doc, section_path=shared_sec)
    c3 = create_reranked_candidate("Section Leave Part 3", reranker_score=0.85, doc_id=shared_doc, section_path=shared_sec)
    c4 = create_reranked_candidate("Other Section Content", reranker_score=0.80, doc_id=shared_doc, section_path="Policy > Health")

    selector = EvidenceSelector(config=CompressionConfig(max_chunks_per_section=2))
    selected_chunks, context_items = selector.select_evidence(chunks=[c1, c2, c3, c4])

    assert len(selected_chunks) == 3
    selected_ids = [c.chunk_id for c in selected_chunks]
    assert c1.chunk_id in selected_ids
    assert c2.chunk_id in selected_ids
    assert c3.chunk_id not in selected_ids
    assert c4.chunk_id in selected_ids


def test_evidence_selector_phase8_contract_structure():
    """
    Verifies that the frozen Phase 8 RAGContextItem strictly adheres to the 8-point contract:
    1. citation_id is deterministic and 1-based.
    2. chunk_id is preserved.
    3. document_id is preserved.
    4. page_number is preserved.
    5. section_path is preserved.
    6. text is exactly the compressed/verbatim evidence.
    7. is_table is preserved.
    8. relevance_score matches the Phase 7 normalized score.
    """
    c = create_reranked_candidate("Evidence sentence for citation", reranker_score=0.98, section_path="Doc > Security")
    c.page_number = 3
    c.is_table = False

    selector = EvidenceSelector()
    _, context_items = selector.select_evidence([c])

    assert len(context_items) == 1
    item = context_items[0]
    assert isinstance(item, RAGContextItem)
    assert item.citation_id == 1
    assert item.chunk_id == c.chunk_id
    assert item.document_id == c.document_id
    assert item.page_number == 3
    assert item.section_path == "Doc > Security"
    assert item.text == c.content
    assert item.is_table is False
    assert item.relevance_score == 0.98


def test_evidence_selector_edge_cases_empty_single_oversized():
    """
    Tests edge cases: empty list, single item, oversized candidate, table protection.
    """
    selector = EvidenceSelector()

    # 1. Empty candidates
    chunks, items = selector.select_evidence([])
    assert chunks == []
    assert items == []

    # 2. Oversized candidate exceeding budget
    c_huge = create_reranked_candidate("Massive chunk text " * 50, reranker_score=0.99, token_count=500)
    chunks_over, items_over = selector.select_evidence([c_huge], max_context_tokens=100)
    assert len(chunks_over) == 0
    assert len(items_over) == 0

    # 3. Table item preserved with is_table flag
    c_table = create_reranked_candidate("| Col A | Col B |\n|---|---|\n| 1 | 2 |", reranker_score=0.92, is_table=True)
    chunks_tbl, items_tbl = selector.select_evidence([c_table])
    assert len(items_tbl) == 1
    assert items_tbl[0].is_table is True
