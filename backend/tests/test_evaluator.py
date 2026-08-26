"""
Unit tests for RetrievalEvaluator IR quality metrics (Recall, Precision, MRR, NDCG).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.app.schemas.retrieval import (
    EvalSample,
    EvaluationReport,
    FusionStrategy,
    HybridRetrievalResponse,
    RetrievalDiagnostics,
    ScoredChunk,
)
from backend.app.services.evaluator import RetrievalEvaluator


@pytest.fixture
def evaluator():
    return RetrievalEvaluator()


def test_metric_computations_exact_math(evaluator):
    """
    Verifies that Recall, Precision, HitRate, MRR, and NDCG match exact IR formulas.
    """
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    c3 = uuid.uuid4()
    c4 = uuid.uuid4()

    # Retrieved rank: [c1, c2, c3, c4]
    # Expected relevant: [c2, c3]
    # At K=3:
    # Retrieved in top 3: [c1, c2, c3]
    # Hits: c2 (rank 2), c3 (rank 3) -> 2 hits out of 2 expected
    # Recall@3 = 2 / 2 = 1.0
    # Precision@3 = 2 / 3 = 0.6667
    # HitRate@3 = 1.0
    # MRR = 1 / 2 = 0.5 (first relevant item c2 is at rank 2)
    metrics = evaluator.compute_metrics(
        retrieved_ids=[c1, c2, c3, c4],
        expected_ids=[c2, c3],
        k=3,
    )

    assert metrics["recall"] == 1.0
    assert pytest.approx(metrics["precision"], rel=1e-3) == 2.0 / 3.0
    assert metrics["hit_rate"] == 1.0
    assert metrics["mrr"] == 0.5
    assert metrics["ndcg"] > 0.0


def test_ndcg_graded_relevance(evaluator):
    """
    Verifies that NDCG properly reflects graded relevance ranks.
    """
    c_high = uuid.uuid4()
    c_low = uuid.uuid4()

    # Case 1: Ideal ranking [c_high, c_low]
    metrics_ideal = evaluator.compute_metrics(
        retrieved_ids=[c_high, c_low],
        expected_ids=[c_high, c_low],
        relevance_grades={str(c_high): 2.0, str(c_low): 1.0},
        k=2,
    )
    assert metrics_ideal["ndcg"] == 1.0

    # Case 2: Sub-optimal ranking [c_low, c_high]
    metrics_sub = evaluator.compute_metrics(
        retrieved_ids=[c_low, c_high],
        expected_ids=[c_high, c_low],
        relevance_grades={str(c_high): 2.0, str(c_low): 1.0},
        k=2,
    )
    assert metrics_sub["ndcg"] < 1.0
    assert metrics_sub["ndcg"] > 0.0


@pytest.mark.asyncio
async def test_evaluate_dataset_aggregation(evaluator):
    """
    Verifies that evaluate_dataset aggregates metrics across a multi-sample dataset.
    """
    doc_id = uuid.uuid4()
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()

    dataset = [
        EvalSample(query="Q1", expected_chunk_ids=[c1]),
        EvalSample(query="Q2", expected_chunk_ids=[c2]),
    ]

    # Mock retriever
    mock_retriever = MagicMock()

    chunk1 = ScoredChunk(
        chunk_id=c1,
        document_id=doc_id,
        content="P1",
        final_score=0.9,
        explanation="test",
    )
    diag = RetrievalDiagnostics(
        query="Q",
        query_type="keyword_search",
        dense_latency_ms=1.0,
        sparse_latency_ms=1.0,
        fusion_latency_ms=1.0,
        total_latency_ms=3.0,
        dense_candidates_count=1,
        sparse_candidates_count=1,
        merged_candidates_count=1,
        fusion_strategy="rrf",
        degraded_mode=False,
    )

    mock_retriever.retrieve = AsyncMock(
        return_value=HybridRetrievalResponse(
            results=[chunk1],
            diagnostics=diag,
        )
    )

    report = await evaluator.evaluate_dataset(
        dataset=dataset,
        retriever=mock_retriever,
        strategy=FusionStrategy.RRF,
        k=5,
    )

    assert isinstance(report, EvaluationReport)
    assert report.total_queries == 2
    assert report.k == 5
    # Q1 had c1 retrieved at rank 1 -> Recall 1.0. Q2 had c1 retrieved (expected c2) -> Recall 0.0.
    # Avg recall = (1.0 + 0.0) / 2 = 0.5
    assert report.recall_at_k == 0.5
    assert report.hit_rate_at_k == 0.5
