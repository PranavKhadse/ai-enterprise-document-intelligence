"""
Integration tests for RAGPipelineService.
Verifies multi-stage pipeline flow: Phase 6 Hybrid Retrieval -> Phase 7 Reranking -> Phase 8 Grounded Synthesis.
"""
import uuid
import pytest
from backend.app.schemas.rag import GroundingStatus, RAGAnswer, RAGQueryRequest
from backend.app.schemas.reranking import (
    RAGContextItem,
    RerankedChunk,
    RerankedRetrievalResponse,
    RerankingDiagnostics,
)
from backend.app.schemas.retrieval import HybridRetrievalResponse, RetrievalDiagnostics, ScoredChunk
from backend.app.services.rag_pipeline import RAGPipelineService
from backend.app.services.rag_synthesis import RAGSynthesisService


class MockHybridRetriever:
    async def retrieve(self, query: str, filter=None, final_top_k=None, **kwargs):
        chunks = [
            ScoredChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                content="Enterprise security mandates multi-factor authentication starting v2.4.0.",
                final_score=0.95,
                dense_score=0.92,
                sparse_score=8.5,
                explanation="Top rank",
            ),
            ScoredChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                content="Database backups are retained for 30 days in cold storage.",
                final_score=0.88,
                dense_score=0.85,
                sparse_score=7.2,
                explanation="Second rank",
            ),
        ]
        return HybridRetrievalResponse(
            results=chunks,
            diagnostics=RetrievalDiagnostics(
                query=query,
                query_type="semantic_question",
                fusion_strategy="rrf",
            ),
        )


class MockRerankingPipeline:
    async def process(self, query: str, retrieval_response: HybridRetrievalResponse, top_k=None, max_context_tokens=None, **kwargs):
        chunks = retrieval_response.results
        context_items = [
            RAGContextItem(
                citation_id=idx + 1,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_title="Policy.pdf",
                page_number=idx + 1,
                section_path="Section > Sub",
                text=c.content,
                relevance_score=c.final_score,
                is_table=False,
            )
            for idx, c in enumerate(chunks)
        ]
        return RerankedRetrievalResponse(
            results=[],
            context_items=context_items,
            diagnostics=RerankingDiagnostics(
                query=query,
                reranker_model="mock-cross-encoder",
                total_phase7_latency_ms=5.0,
                phase6_diagnostics=retrieval_response.diagnostics,
            ),
        )


@pytest.mark.asyncio
async def test_rag_pipeline_end_to_end_execution():
    """Verifies that RAGPipelineService successfully coordinates Phase 6 -> Phase 7 -> Phase 8."""
    pipeline = RAGPipelineService(
        retriever=MockHybridRetriever(),
        reranker=MockRerankingPipeline(),
        synthesis=RAGSynthesisService(),
    )

    request = RAGQueryRequest(
        query="What is the security and backup policy?",
        top_k=5,
        max_context_tokens=1200,
        enable_verification=True,
    )

    answer = await pipeline.query(request)

    assert isinstance(answer, RAGAnswer)
    assert answer.grounding_status in {GroundingStatus.FULLY_GROUNDED, GroundingStatus.PARTIALLY_GROUNDED}
    assert len(answer.citations) >= 1
    assert answer.diagnostics.phase7_diagnostics is not None
    assert answer.diagnostics.phase7_diagnostics.reranker_model == "mock-cross-encoder"


@pytest.mark.asyncio
async def test_rag_pipeline_empty_query():
    """Verifies pipeline behavior on empty query string."""
    pipeline = RAGPipelineService()
    request = RAGQueryRequest(query="   ")
    answer = await pipeline.query(request)

    assert answer.insufficient_evidence is True
    assert len(answer.citations) == 0
