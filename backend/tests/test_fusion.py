"""
Unit tests for FusionEngine (Reciprocal Rank Fusion & Normalized Weighted Score Fusion).
"""
import uuid
import pytest
from backend.app.schemas.bm25 import BM25SearchResult
from backend.app.schemas.embedding import VectorSearchResult
from backend.app.schemas.retrieval import FusionStrategy
from backend.app.services.fusion import FusionEngine


@pytest.fixture
def fusion():
    return FusionEngine()


def test_rrf_mathematical_calculation(fusion):
    """
    Verifies that RRF score matches the mathematical formula:
    RRF(d) = w_dense / (k + rank_dense) + w_sparse / (k + rank_sparse)
    """
    doc_id = uuid.uuid4()
    c1_id = uuid.uuid4()
    c2_id = uuid.uuid4()

    # Dense: c1 is rank 1, c2 is rank 2
    dense_candidates = [
        VectorSearchResult(chunk_id=c1_id, document_id=doc_id, score=0.92, content="Passage 1"),
        VectorSearchResult(chunk_id=c2_id, document_id=doc_id, score=0.81, content="Passage 2"),
    ]

    # Sparse: c2 is rank 1, c1 is rank 2
    sparse_candidates = [
        BM25SearchResult(chunk_id=c2_id, document_id=doc_id, score=12.5, content="Passage 2"),
        BM25SearchResult(chunk_id=c1_id, document_id=doc_id, score=9.8, content="Passage 1"),
    ]

    # k = 60, w_dense = 0.6, w_sparse = 0.4
    # Expected c1: 0.6 / (60 + 1) + 0.4 / (60 + 2) = 0.6/61 + 0.4/62 = 0.00983606 + 0.00645161 = 0.01628767
    # Expected c2: 0.6 / (60 + 2) + 0.4 / (60 + 1) = 0.6/62 + 0.4/61 = 0.00967742 + 0.00655738 = 0.01623480
    # c1 should be rank 1 because dense weight (0.6) > sparse weight (0.4)
    results = fusion.reciprocal_rank_fusion(
        dense_candidates=dense_candidates,
        sparse_candidates=sparse_candidates,
        rrf_k=60,
        dense_weight=0.6,
        sparse_weight=0.4,
        final_top_k=5,
    )

    assert len(results) == 2
    assert results[0].chunk_id == c1_id
    assert results[1].chunk_id == c2_id

    expected_c1_score = (0.6 / 61) + (0.4 / 62)
    assert pytest.approx(results[0].final_score, rel=1e-4) == expected_c1_score
    assert "dense" in results[0].retrieval_methods and "bm25" in results[0].retrieval_methods


def test_rrf_missing_candidate_handling(fusion):
    """
    Verifies that a candidate only present in one list gets a score from that list only.
    """
    doc_id = uuid.uuid4()
    c_dense_only = uuid.uuid4()
    c_sparse_only = uuid.uuid4()

    dense_candidates = [
        VectorSearchResult(chunk_id=c_dense_only, document_id=doc_id, score=0.88, content="Dense only content"),
    ]
    sparse_candidates = [
        BM25SearchResult(chunk_id=c_sparse_only, document_id=doc_id, score=15.0, content="Sparse only content"),
    ]

    results = fusion.reciprocal_rank_fusion(
        dense_candidates=dense_candidates,
        sparse_candidates=sparse_candidates,
        rrf_k=60,
        dense_weight=0.6,
        sparse_weight=0.4,
    )

    assert len(results) == 2
    # Dense only: 0.6 / 61 = 0.009836
    # Sparse only: 0.4 / 61 = 0.006557
    assert results[0].chunk_id == c_dense_only
    assert results[0].retrieval_methods == ["dense"]
    assert results[1].chunk_id == c_sparse_only
    assert results[1].retrieval_methods == ["bm25"]


def test_weighted_score_fusion_normalization(fusion):
    """
    Verifies that Min-Max normalization scales raw scores to [0.0, 1.0] before weighted combination.
    """
    doc_id = uuid.uuid4()
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()

    dense_candidates = [
        VectorSearchResult(chunk_id=c1, document_id=doc_id, score=0.90, content="Content 1"),
        VectorSearchResult(chunk_id=c2, document_id=doc_id, score=0.70, content="Content 2"),
    ]
    # Dense min=0.70, max=0.90 -> c1 norm = 1.0, c2 norm = 0.0

    sparse_candidates = [
        BM25SearchResult(chunk_id=c2, document_id=doc_id, score=20.0, content="Content 2"),
        BM25SearchResult(chunk_id=c1, document_id=doc_id, score=10.0, content="Content 1"),
    ]
    # Sparse min=10.0, max=20.0 -> c2 norm = 1.0, c1 norm = 0.0

    # With w_dense=0.5, w_sparse=0.5:
    # c1 fused = 0.5 * 1.0 + 0.5 * 0.0 = 0.5
    # c2 fused = 0.5 * 0.0 + 0.5 * 1.0 = 0.5
    results = fusion.weighted_score_fusion(
        dense_candidates=dense_candidates,
        sparse_candidates=sparse_candidates,
        dense_weight=0.5,
        sparse_weight=0.5,
    )

    assert len(results) == 2
    assert pytest.approx(results[0].final_score, rel=1e-4) == 0.5
    assert pytest.approx(results[1].final_score, rel=1e-4) == 0.5


def test_deterministic_tie_breaking(fusion):
    """
    Verifies that items with identical final scores break ties deterministically on raw scores.
    """
    doc_id = uuid.uuid4()
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()

    # Equal dense ranks and sparse ranks
    dense_candidates = [
        VectorSearchResult(chunk_id=c1, document_id=doc_id, score=0.95, content="Passage 1"),
        VectorSearchResult(chunk_id=c2, document_id=doc_id, score=0.85, content="Passage 2"),
    ]
    sparse_candidates = [
        BM25SearchResult(chunk_id=c2, document_id=doc_id, score=10.0, content="Passage 2"),
        BM25SearchResult(chunk_id=c1, document_id=doc_id, score=10.0, content="Passage 1"),
    ]

    results = fusion.reciprocal_rank_fusion(
        dense_candidates=dense_candidates,
        sparse_candidates=sparse_candidates,
        rrf_k=60,
        dense_weight=0.5,
        sparse_weight=0.5,
    )

    # c1 and c2 will have equal RRF score, but c1 has higher raw dense score (0.95 vs 0.85)
    assert len(results) == 2
    assert results[0].chunk_id == c1
    assert results[1].chunk_id == c2
