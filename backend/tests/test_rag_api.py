"""
API integration tests for Grounded RAG Query endpoint (POST /api/v1/rag/query).
Verifies route registration, request validation, structured response delivery, and telemetry handling.
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app
from backend.app.schemas.rag import GroundingStatus, RAGAnswer
from backend.app.schemas.reranking import (
    RAGContextItem,
    RerankedRetrievalResponse,
    RerankingDiagnostics,
)
from backend.app.schemas.retrieval import HybridRetrievalResponse, RetrievalDiagnostics, ScoredChunk
from backend.app.services.rag_pipeline import RAGPipelineService, rag_pipeline_service
from backend.app.services.rag_synthesis import RAGSynthesisService


class StubHybridRetriever:
    async def retrieve(self, query: str, filter=None, final_top_k=None, **kwargs):
        chunks = [
            ScoredChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                content="Multi-factor authentication is mandatory starting v2.4.0.",
                final_score=0.95,
                explanation="Top rank",
            )
        ]
        return HybridRetrievalResponse(
            results=chunks,
            diagnostics=RetrievalDiagnostics(query=query, query_type="semantic_question", fusion_strategy="rrf"),
        )


class StubRerankingPipeline:
    async def process(self, query: str, retrieval_response: HybridRetrievalResponse, **kwargs):
        items = [
            RAGContextItem(
                citation_id=1,
                chunk_id=retrieval_response.results[0].chunk_id,
                document_id=retrieval_response.results[0].document_id,
                document_title="Security.pdf",
                page_number=4,
                section_path="Auth",
                text=retrieval_response.results[0].content,
                relevance_score=0.95,
                is_table=False,
            )
        ]
        return RerankedRetrievalResponse(
            results=[],
            context_items=items,
            diagnostics=RerankingDiagnostics(query=query, reranker_model="stub-model"),
        )


@pytest.fixture
def mock_rag_pipeline(monkeypatch):
    stub_pipeline = RAGPipelineService(
        retriever=StubHybridRetriever(),
        reranker=StubRerankingPipeline(),
        synthesis=RAGSynthesisService(),
    )
    # Monkeypatch the global rag_pipeline_service instance
    monkeypatch.setattr("backend.app.api.v1.endpoints.rag.rag_pipeline_service", stub_pipeline)
    return stub_pipeline


@pytest.mark.asyncio
async def test_api_rag_query_success(mock_rag_pipeline):
    """Verifies successful RAG query endpoint response with HTTP 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rag/query",
            json={
                "query": "What is the authentication requirement?",
                "temperature": 0.0,
                "enable_verification": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["grounding_status"] in ["fully_grounded", "partially_grounded"]
        assert len(data["citations"]) >= 1
        assert data["citations"][0]["document_title"] == "Security.pdf"
        assert "diagnostics" in data
        assert data["diagnostics"]["evidence_count"] >= 1


@pytest.mark.asyncio
async def test_api_rag_query_empty_string():
    """Verifies that an empty query string is rejected with HTTP 422 Unprocessable Entity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rag/query",
            json={"query": ""},
        )
        assert response.status_code == 422
