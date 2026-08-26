"""
Unit tests for CrossEncoderRerankerService.
Verifies batch inference, deterministic tie-breaking, rank delta computation,
and offline mock capability.
"""
import uuid
from typing import List, Optional
import pytest
from backend.app.schemas.reranking import RerankerConfig
from backend.app.schemas.retrieval import ScoredChunk
from backend.app.services.cross_encoder import CrossEncoderRerankerService


def create_mock_scored_chunk(
    content: str,
    final_score: float,
    chunk_id: Optional[uuid.UUID] = None,
    section_path: str = "Root > Section",
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        final_score=final_score,
        section_path=section_path,
        explanation="Phase 6 candidate",
    )


def test_cross_encoder_empty_candidates():
    """
    Verifies that empty candidate list returns empty list immediately without error.
    """
    reranker = CrossEncoderRerankerService()
    results = reranker.rerank_sync(query="test query", candidates=[])
    assert results == []


def test_cross_encoder_deterministic_ranking_and_rank_delta():
    """
    Verifies that cross-encoder correctly reorders candidates based on mock raw logits,
    calculates rank_delta, and preserves initial Phase 6 scores.
    """
    c1 = create_mock_scored_chunk("Candidate 1 (low relevance)", final_score=0.9)
    c2 = create_mock_scored_chunk("Candidate 2 (high relevance)", final_score=0.8)
    c3 = create_mock_scored_chunk("Candidate 3 (medium relevance)", final_score=0.7)

    # Custom mock inference scoring: c2 (+5.0) > c3 (+2.0) > c1 (-3.0)
    def mock_inference(query: str, passages: List[str]) -> List[float]:
        score_map = {
            "Candidate 1 (low relevance)": -3.0,
            "Candidate 2 (high relevance)": 5.0,
            "Candidate 3 (medium relevance)": 2.0,
        }
        return [score_map[p] for p in passages]

    reranker = CrossEncoderRerankerService(custom_inference_fn=mock_inference)
    results = reranker.rerank_sync(
        query="What is high relevance?",
        candidates=[c1, c2, c3],
        top_k=3,
    )

    assert len(results) == 3
    # Rank 1: c2 (was rank 2 in Phase 6, now rank 1 -> rank_delta = +1)
    assert results[0].chunk_id == c2.chunk_id
    assert results[0].reranker_raw_score == 5.0
    assert results[0].reranker_rank == 1
    assert results[0].initial_retrieval_rank == 2
    assert results[0].rank_delta == 1
    assert results[0].reranker_score > 0.99  # sigmoid(5.0)

    # Rank 2: c3 (was rank 3, now rank 2 -> rank_delta = +1)
    assert results[1].chunk_id == c3.chunk_id
    assert results[1].reranker_raw_score == 2.0
    assert results[1].reranker_rank == 2
    assert results[1].initial_retrieval_rank == 3
    assert results[1].rank_delta == 1

    # Rank 3: c1 (was rank 1, now rank 3 -> rank_delta = -2)
    assert results[2].chunk_id == c1.chunk_id
    assert results[2].reranker_raw_score == -3.0
    assert results[2].reranker_rank == 3
    assert results[2].initial_retrieval_rank == 1
    assert results[2].rank_delta == -2


def test_cross_encoder_deterministic_tie_breaking():
    """
    Verifies 3-level tie breaking:
    1. reranker_raw_score DESC
    2. initial_retrieval_score DESC
    3. chunk_id ASC
    """
    id_low = uuid.UUID("11111111-0000-0000-0000-000000000001")
    id_high = uuid.UUID("11111111-0000-0000-0000-000000000002")

    # Both have identical Phase 6 final_score and identical mock logit score
    c_low = create_mock_scored_chunk("Text A", final_score=0.8, chunk_id=id_low)
    c_high = create_mock_scored_chunk("Text B", final_score=0.8, chunk_id=id_high)

    def mock_tie_inference(query: str, passages: List[str]) -> List[float]:
        return [2.5, 2.5]

    reranker = CrossEncoderRerankerService(custom_inference_fn=mock_tie_inference)
    results = reranker.rerank_sync(
        query="query",
        candidates=[c_high, c_low],
        top_k=2,
    )

    # id_low should sort before id_high on tie
    assert results[0].chunk_id == id_low
    assert results[1].chunk_id == id_high


def test_cross_encoder_candidate_window_slicing():
    """
    Verifies that only the top candidate_window_size items are evaluated by the cross-encoder.
    """
    candidates = [
        create_mock_scored_chunk(f"Candidate {i}", final_score=1.0 - i * 0.05)
        for i in range(10)
    ]

    evaluated_passages: List[str] = []

    def mock_capture(query: str, passages: List[str]) -> List[float]:
        nonlocal evaluated_passages
        evaluated_passages.extend(passages)
        return [1.0] * len(passages)

    reranker = CrossEncoderRerankerService(custom_inference_fn=mock_capture)
    reranker.rerank_sync(
        query="test query",
        candidates=candidates,
        top_k=3,
        candidate_window_size=4,
    )

    # Exactly 4 candidates should have been evaluated
    assert len(evaluated_passages) == 4
