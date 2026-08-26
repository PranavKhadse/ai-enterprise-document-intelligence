"""
Integration tests for HybridRetrievalService.
"""
import uuid
from unittest.mock import MagicMock
import pytest
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models import Department, Document, DocumentChunk
from backend.app.schemas.bm25 import BM25Config
from backend.app.schemas.retrieval import FusionStrategy, HybridRetrievalResponse, RetrievalFilter
from backend.app.services.bm25 import BM25IndexService
from backend.app.services.dual_indexer import DualIndexingService
from backend.app.services.embedding import embedding_service
from backend.app.services.fusion import FusionEngine
from backend.app.services.hybrid_retriever import HybridRetrievalError, HybridRetrievalService
from backend.app.services.indexer import IndexingService
from backend.app.services.query_analyzer import QueryAnalyzer
from backend.app.services.vector_store import VectorStoreService


@pytest.fixture
def isolated_hybrid_stack(tmp_path):
    """Provides isolated Qdrant, BM25, DualIndexer, and HybridRetriever instances."""
    qdrant_client = QdrantClient(location=":memory:")
    vector_service = VectorStoreService(client=qdrant_client, collection_name="test_hybrid_col")
    dense_indexer = IndexingService(embed_service=embedding_service, store_service=vector_service)

    bm25_cfg = BM25Config(index_path=str(tmp_path / "hybrid_bm25.pkl"), auto_persist=False)
    sparse_indexer = BM25IndexService(config=bm25_cfg)

    dual_indexer = DualIndexingService(dense_indexer=dense_indexer, sparse_indexer=sparse_indexer)
    analyzer = QueryAnalyzer()
    fusion = FusionEngine()

    retriever = HybridRetrievalService(
        vector_service=vector_service,
        embed_service=embedding_service,
        sparse_service=sparse_indexer,
        analyzer=analyzer,
        fusion=fusion,
    )

    return {
        "retriever": retriever,
        "dual_indexer": dual_indexer,
        "vector_service": vector_service,
        "sparse_service": sparse_indexer,
    }


@pytest.mark.asyncio
async def test_end_to_end_hybrid_retrieval(isolated_hybrid_stack):
    """
    Verifies full integration flow: PostgreSQL chunks -> Dual Ingestion -> Hybrid Retrieval.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(bind=test_async_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = uuid.uuid4()
    dept_id = uuid.uuid4()

    async with test_async_session() as session:
        dept = Department(id=dept_id, name="Operations")
        session.add(dept)

        doc = Document(
            id=doc_id,
            title="Standard Operating Procedures",
            file_path="/tmp/sop.pdf",
            file_hash="sop_hash",
            file_type="pdf",
            department_id=dept_id,
        )
        session.add(doc)

        c1 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="Standard network configuration requires adherence to specification RFC-4821.",
            section_path="Network",
            page_number=1,
            token_count=12,
        )
        c2 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=1,
            content="Employees are allocated 25 days of annual paid leave.",
            section_path="HR > Leave",
            page_number=2,
            token_count=10,
        )
        session.add_all([c1, c2])
        await session.commit()

        # Ingest into Qdrant + BM25
        dual_indexer = isolated_hybrid_stack["dual_indexer"]
        ingest_res = await dual_indexer.index_document(document_id=doc_id, db=session)
        assert ingest_res.success is True

        retriever: HybridRetrievalService = isolated_hybrid_stack["retriever"]

        # Exact identifier search
        resp = await retriever.retrieve(query="What is RFC-4821?")
        assert isinstance(resp, HybridRetrievalResponse)
        assert len(resp.results) >= 1
        assert resp.results[0].chunk_id == c1.id
        assert "RFC-4821" in resp.results[0].content
        assert resp.diagnostics.degraded_mode is False

        # Semantic question search
        resp_semantic = await retriever.retrieve(query="How many vacation days do workers receive?")
        assert len(resp_semantic.results) >= 1
        assert resp_semantic.results[0].chunk_id == c2.id
        assert "annual paid leave" in resp_semantic.results[0].content

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_metadata_filtering_consistency(isolated_hybrid_stack):
    """
    Verifies that department_id filters are applied identically across both backends.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(bind=test_async_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    dept_a = uuid.uuid4()
    dept_b = uuid.uuid4()

    async with test_async_session() as session:
        session.add_all([Department(id=dept_a, name="Dept A"), Department(id=dept_b, name="Dept B")])

        doc_a = Document(id=uuid.uuid4(), title="Doc A", file_path="/tmp/a.pdf", file_hash="ha", file_type="pdf", department_id=dept_a)
        doc_b = Document(id=uuid.uuid4(), title="Doc B", file_path="/tmp/b.pdf", file_hash="hb", file_type="pdf", department_id=dept_b)
        session.add_all([doc_a, doc_b])

        c_a = DocumentChunk(id=uuid.uuid4(), document_id=doc_a.id, chunk_index=0, content="Safety protocol alpha.")
        c_b = DocumentChunk(id=uuid.uuid4(), document_id=doc_b.id, chunk_index=0, content="Safety protocol beta.")
        session.add_all([c_a, c_b])
        await session.commit()

        dual_indexer = isolated_hybrid_stack["dual_indexer"]
        await dual_indexer.index_document(doc_a.id, db=session)
        await dual_indexer.index_document(doc_b.id, db=session)

        retriever: HybridRetrievalService = isolated_hybrid_stack["retriever"]

        # Search with Dept A filter
        filter_a = RetrievalFilter(department_id=dept_a)
        resp_a = await retriever.retrieve(query="safety protocol", filter=filter_a)
        assert len(resp_a.results) == 1
        assert resp_a.results[0].chunk_id == c_a.id

        # Search with Dept B filter
        filter_b = RetrievalFilter(department_id=dept_b)
        resp_b = await retriever.retrieve(query="safety protocol", filter=filter_b)
        assert len(resp_b.results) == 1
        assert resp_b.results[0].chunk_id == c_b.id

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_degraded_mode_fallback(isolated_hybrid_stack):
    """
    Verifies that when one backend encounters an exception, the system gracefully falls back
    to the other backend with degraded_mode=True and warning notes.
    """
    retriever: HybridRetrievalService = isolated_hybrid_stack["retriever"]

    # Mock Dense backend failure
    retriever.vector_service.search_vectors = MagicMock(side_effect=Exception("Simulated Qdrant timeout"))

    # Populate BM25 with a chunk
    doc = Document(id=uuid.uuid4(), title="Degraded Test")
    c1 = DocumentChunk(id=uuid.uuid4(), document_id=doc.id, chunk_index=0, content="Emergency fallback protocol.")
    isolated_hybrid_stack["sparse_service"].index_chunks([c1], doc)

    resp = await retriever.retrieve(query="emergency protocol")
    assert resp.diagnostics.degraded_mode is True
    assert len(resp.diagnostics.warnings) >= 1
    assert "Dense vector retrieval failed" in resp.diagnostics.warnings[0]
    assert len(resp.results) == 1
    assert resp.results[0].chunk_id == c1.id


@pytest.mark.asyncio
async def test_both_backends_failure_raises_error(isolated_hybrid_stack):
    """
    Verifies that when both backends fail simultaneously, HybridRetrievalError is raised.
    """
    retriever: HybridRetrievalService = isolated_hybrid_stack["retriever"]
    retriever.vector_service.search_vectors = MagicMock(side_effect=Exception("Dense down"))
    retriever.sparse_service.search = MagicMock(side_effect=Exception("Sparse down"))

    with pytest.raises(HybridRetrievalError) as exc_info:
        await retriever.retrieve(query="any query")

    assert "Both retrieval backends failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_empty_query_returns_empty_response(isolated_hybrid_stack):
    """
    Verifies that empty string or whitespace queries return empty results cleanly.
    """
    retriever: HybridRetrievalService = isolated_hybrid_stack["retriever"]
    resp = await retriever.retrieve(query="")
    assert resp.results == []
    assert resp.diagnostics.dense_candidates_count == 0
    assert resp.diagnostics.sparse_candidates_count == 0
