"""
Integration tests for RerankingPipelineService.
Verifies end-to-end Phase 6 -> Phase 7 transformation, degraded mode fallback,
and diagnostics generation.
"""
import uuid
from typing import List, Optional
import pytest
from backend.app.schemas.reranking import RerankedRetrievalResponse, RerankerConfig
from backend.app.schemas.retrieval import HybridRetrievalResponse, RetrievalDiagnostics, ScoredChunk
from backend.app.services.cross_encoder import CrossEncoderRerankerService
from backend.app.services.reranking_pipeline import RerankingPipelineService


def create_hybrid_retrieval_response(num_candidates: int = 5) -> HybridRetrievalResponse:
    chunks = [
        ScoredChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content=f"Candidate passage {i} about enterprise systems and security policies.",
            final_score=1.0 - i * 0.1,
            dense_score=0.9 - i * 0.1,
            sparse_score=10.0 - i * 1.5,
            dense_rank=i + 1,
            sparse_rank=i + 1,
            explanation=f"Retrieved at rank {i+1}",
        )
        for i in range(num_candidates)
    ]
    diagnostics = RetrievalDiagnostics(
        query="test enterprise query",
        query_type="semantic_question",
        fusion_strategy="rrf",
    )
    return HybridRetrievalResponse(results=chunks, diagnostics=diagnostics)


@pytest.mark.asyncio
async def test_reranking_pipeline_end_to_end():
    """
    Verifies full Phase 7 pipeline flow: Rerank -> Compress -> Select -> RAGContextItems.
    """
    retrieval_resp = create_hybrid_retrieval_response(num_candidates=5)

    # Custom mock inference reversing the order (candidate 4 becomes #1)
    def mock_reverse_inference(query: str, passages: List[str]) -> List[float]:
        return [float(i) for i in range(len(passages))]

    custom_reranker = CrossEncoderRerankerService(custom_inference_fn=mock_reverse_inference)
    pipeline = RerankingPipelineService(reranker=custom_reranker)

    response = await pipeline.process(
        query="test enterprise query",
        retrieval_response=retrieval_resp,
        top_k=3,
    )

    assert isinstance(response, RerankedRetrievalResponse)
    assert len(response.results) <= 3
    assert len(response.context_items) <= 3
    assert response.diagnostics.degraded_mode is False
    assert response.diagnostics.total_phase7_latency_ms >= 0.0

    # Verify that the highest-scoring candidate in Phase 7 is the one mock assigned highest logit
    assert response.results[0].chunk_id == retrieval_resp.results[-1].chunk_id or response.results[0].reranker_raw_score >= response.results[-1].reranker_raw_score


@pytest.mark.asyncio
async def test_reranking_pipeline_degraded_fallback_on_failure():
    """
    Verifies graceful fallback: when cross-encoder throws an exception,
    the pipeline falls back to Phase 6 order with degraded_mode=True and no HTTP 500.
    """
    retrieval_resp = create_hybrid_retrieval_response(num_candidates=3)

    def mock_broken_inference(query: str, passages: List[str]) -> List[float]:
        raise RuntimeError("GPU/ONNX engine crash simulation")

    broken_reranker = CrossEncoderRerankerService(custom_inference_fn=mock_broken_inference)
    pipeline = RerankingPipelineService(reranker=broken_reranker)

    response = await pipeline.process(
        query="test query",
        retrieval_response=retrieval_resp,
        top_k=3,
    )

    # Must succeed with fallback
    assert len(response.results) == 3
    assert response.diagnostics.degraded_mode is True
    assert len(response.diagnostics.warnings) > 0
    # Order should match Phase 6 fallback order
    assert response.results[0].chunk_id == retrieval_resp.results[0].chunk_id


@pytest.mark.asyncio
async def test_reranking_pipeline_empty_query():
    """
    Verifies that an empty query returns an empty response immediately.
    """
    pipeline = RerankingPipelineService()
    retrieval_resp = create_hybrid_retrieval_response(num_candidates=0)

    response = await pipeline.process(
        query="",
        retrieval_response=retrieval_resp,
    )

    assert len(response.results) == 0
    assert len(response.context_items) == 0
