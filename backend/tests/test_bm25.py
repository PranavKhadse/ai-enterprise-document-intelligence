"""
Unit and Integration tests for BM25 Sparse Lexical Search Service.
"""
import uuid
import pytest
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.bm25 import BM25Config, BM25SearchResult
from backend.app.services.bm25 import BM25Error, BM25IndexService


@pytest.fixture
def bm25_service_instance(tmp_path):
    """Creates an isolated BM25IndexService instance using temporary index path."""
    cfg = BM25Config(
        k1=1.5,
        b=0.75,
        index_path=str(tmp_path / "test_bm25.pkl"),
        auto_persist=False,
    )
    return BM25IndexService(config=cfg)


def test_enterprise_token_preservation(bm25_service_instance):
    """
    Verifies that the tokenizer preserves technical codes, version tags, and enterprise identifiers.
    """
    sample_text = (
        "Please refer to specification RFC-4821 and compliance standard ISO-9001. "
        "Upgrade to firmware v2.1.0 to resolve error_500 in module C++ under Clause_3.1 for tax Form W-2."
    )
    tokens = bm25_service_instance.tokenize(sample_text)

    expected_tokens = [
        "rfc-4821",
        "iso-9001",
        "v2.1.0",
        "error_500",
        "c++",
        "clause_3.1",
        "w-2",
    ]

    for expected in expected_tokens:
        assert expected in tokens, f"Tokenizer failed to preserve enterprise token: {expected}"


def test_bm25_exact_keyword_retrieval(bm25_service_instance):
    """
    Verifies that an exact query for a rare technical code retrieves the matching chunk as top-1.
    """
    doc = Document(id=uuid.uuid4(), title="RFC Spec")

    c1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        content="General guidelines for internet network protocols.",
        section_path="Intro",
    )
    c2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=1,
        content="Path MTU Discovery specification is formally defined in RFC-4821.",
        section_path="Specification",
    )
    c3 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=2,
        content="TCP window size scaling is detailed in RFC-7323.",
        section_path="TCP Scaling",
    )

    bm25_service_instance.index_chunks([c1, c2, c3], doc)

    results = bm25_service_instance.search("RFC-4821", limit=3)
    assert len(results) >= 1
    assert results[0].chunk_id == c2.id
    assert "RFC-4821" in results[0].content


def test_bm25_k1_term_frequency_saturation(bm25_service_instance):
    """
    Verifies that a chunk with higher term frequency scores higher than a chunk with lower term frequency.
    """
    doc = Document(id=uuid.uuid4(), title="Security Policy")

    c1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        content="Compliance is required across all offices.",
    )
    c2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=1,
        content="Compliance compliance compliance is strictly mandated.",
    )

    bm25_service_instance.index_chunks([c1, c2], doc)

    results = bm25_service_instance.search("compliance", limit=2)
    assert len(results) == 2
    assert results[0].chunk_id == c2.id
    assert results[0].score > results[1].score


def test_bm25_b_length_normalization(bm25_service_instance):
    """
    Verifies that with b=0.75, a concise chunk with matching keyword scores higher than a bloated chunk.
    """
    doc = Document(id=uuid.uuid4(), title="Leave Guidelines")

    concise = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        content="Maternity leave entitlement is 26 weeks.",
    )
    bloated = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=1,
        content="Maternity leave is defined as follows. " + ("Here are unrelated company notes and filler text. " * 30),
    )

    bm25_service_instance.index_chunks([concise, bloated], doc)

    results = bm25_service_instance.search("maternity", limit=2)
    assert len(results) == 2
    assert results[0].chunk_id == concise.id
    assert results[0].score > results[1].score


def test_bm25_metadata_and_department_filtering(bm25_service_instance):
    """
    Verifies that searching with a department_id filter excludes chunks from other departments.
    """
    dept_hr = uuid.uuid4()
    dept_eng = uuid.uuid4()

    doc_hr = Document(id=uuid.uuid4(), title="HR Leave", department_id=dept_hr)
    doc_eng = Document(id=uuid.uuid4(), title="Eng Leave", department_id=dept_eng)

    c_hr = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_hr.id,
        chunk_index=0,
        content="Emergency leave policies for HR department employees.",
    )
    c_eng = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_eng.id,
        chunk_index=0,
        content="Emergency on-call leave procedures for Engineering team.",
    )

    bm25_service_instance.index_chunks([c_hr], doc_hr)
    bm25_service_instance.index_chunks([c_eng], doc_eng)

    # Search with HR filter
    results_hr = bm25_service_instance.search("emergency leave", department_id=dept_hr, limit=5)
    assert len(results_hr) == 1
    assert results_hr[0].chunk_id == c_hr.id

    # Search with Engineering filter
    results_eng = bm25_service_instance.search("emergency leave", department_id=dept_eng, limit=5)
    assert len(results_eng) == 1
    assert results_eng[0].chunk_id == c_eng.id


def test_bm25_stale_posting_purging_on_reindex(bm25_service_instance):
    """
    Verifies that re-indexing a document completely removes stale postings and recomputes statistics.
    """
    doc = Document(id=uuid.uuid4(), title="Living Doc")

    old_chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        content="Old keyword zebra and giraffe description.",
    )
    bm25_service_instance.index_chunks([old_chunk], doc)

    assert bm25_service_instance.corpus_size == 1
    assert "zebra" in bm25_service_instance.postings

    # Re-index with completely new content
    new_chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        content="New keyword kangaroo and koala description.",
    )
    bm25_service_instance.index_chunks([new_chunk], doc)

    # Must still have corpus_size = 1 (not 2!)
    assert bm25_service_instance.corpus_size == 1
    # Old keyword must be completely purged from postings
    assert "zebra" not in bm25_service_instance.postings
    assert "kangaroo" in bm25_service_instance.postings

    # Searching old keyword must return []
    assert bm25_service_instance.search("zebra") == []
    # Searching new keyword must find new chunk
    assert len(bm25_service_instance.search("kangaroo")) == 1


def test_bm25_version_isolation(bm25_service_instance):
    """
    Verifies multi-version coexistence and version-isolated deletion.
    """
    doc = Document(id=uuid.uuid4(), title="Versioned Policy")
    v1_id = uuid.uuid4()
    v2_id = uuid.uuid4()

    c_v1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_id=v1_id,
        chunk_index=0,
        content="Version 1: Travel budget allowance is 500 dollars.",
    )
    c_v2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_id=v2_id,
        chunk_index=0,
        content="Version 2: Travel budget allowance is 750 dollars.",
    )

    bm25_service_instance.index_chunks([c_v1], doc)
    bm25_service_instance.index_chunks([c_v2], doc)

    assert bm25_service_instance.corpus_size == 2

    # Filter by Version 1
    res_v1 = bm25_service_instance.search("travel budget", version_id=v1_id)
    assert len(res_v1) == 1
    assert res_v1[0].version_id == v1_id
    assert "500 dollars" in res_v1[0].content

    # Delete Version 1
    bm25_service_instance.delete_by_version(document_id=doc.id, version_id=v1_id)
    assert bm25_service_instance.corpus_size == 1

    # Search again
    res_after = bm25_service_instance.search("travel budget")
    assert len(res_after) == 1
    assert res_after[0].version_id == v2_id


def test_bm25_atomic_disk_persistence_and_reload(tmp_path):
    """
    Verifies that atomic persistence to disk and reloading into a fresh instance restores exact rankings.
    """
    index_file = tmp_path / "bm25_persisted.pkl"
    cfg = BM25Config(index_path=str(index_file), auto_persist=True)
    svc1 = BM25IndexService(config=cfg)

    doc = Document(id=uuid.uuid4(), title="Handbook")
    c1 = DocumentChunk(id=uuid.uuid4(), document_id=doc.id, chunk_index=0, content="Encryption standards.")
    svc1.index_chunks([c1], doc)

    assert index_file.exists()

    # Load in new instance
    svc2 = BM25IndexService(config=cfg, auto_load=True)
    assert svc2.corpus_size == 1
    results = svc2.search("encryption")
    assert len(results) == 1
    assert results[0].chunk_id == c1.id


def test_bm25_empty_query_and_unknown_terms(bm25_service_instance):
    """
    Verifies that empty query or searching for non-existent terms returns [] cleanly.
    """
    assert bm25_service_instance.search("") == []
    assert bm25_service_instance.search("nonexistenttermXYZ123") == []
