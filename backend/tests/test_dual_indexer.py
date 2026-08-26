"""
End-to-end integration tests for DualIndexingService (Qdrant + BM25).
"""
import uuid
from unittest.mock import MagicMock
import pytest
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models import Department, Document, DocumentChunk
from backend.app.schemas.bm25 import BM25Config, DualIndexingResult
from backend.app.services.bm25 import BM25IndexService
from backend.app.services.dual_indexer import DualIndexingService
from backend.app.services.embedding import embedding_service
from backend.app.services.indexer import IndexingService
from backend.app.services.vector_store import VectorStoreService


@pytest.fixture
def isolated_dual_indexer(tmp_path):
    """Provides an isolated DualIndexingService with in-memory Qdrant and temporary BM25 index."""
    qdrant_client = QdrantClient(location=":memory:")
    vector_service = VectorStoreService(client=qdrant_client, collection_name="test_dual_collection")
    dense_indexer = IndexingService(embed_service=embedding_service, store_service=vector_service)

    bm25_cfg = BM25Config(index_path=str(tmp_path / "dual_bm25.pkl"), auto_persist=False)
    sparse_indexer = BM25IndexService(config=bm25_cfg)

    return DualIndexingService(dense_indexer=dense_indexer, sparse_indexer=sparse_indexer)


@pytest.mark.asyncio
async def test_dual_indexing_service_end_to_end(isolated_dual_indexer):
    """
    Test full end-to-end flow: PostgreSQL chunks -> DualIndexingService -> Qdrant + BM25.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = uuid.uuid4()
    dept_id = uuid.uuid4()

    async with test_async_session() as session:
        dept = Department(id=dept_id, name="Security & Compliance")
        session.add(dept)

        doc = Document(
            id=doc_id,
            title="ISO Compliance Manual",
            file_path="/tmp/iso.pdf",
            file_hash="hash_iso",
            file_type="pdf",
            department_id=dept_id,
        )
        session.add(doc)

        c1 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="[Context: ISO Spec] Information security controls follow ISO-27001 specification.",
            page_number=1,
            section_path="ISO Spec",
            metadata_json={"page_numbers": [1], "is_table": False},
            token_count=12,
        )
        session.add(c1)
        await session.commit()

        # Execute Dual Indexing
        result = await isolated_dual_indexer.index_document(document_id=doc_id, version_id=None, db=session)

        assert isinstance(result, DualIndexingResult)
        assert result.success is True
        assert result.dense_indexed_count == 1
        assert result.sparse_indexed_count == 1
        assert result.error is None

        # Verify Qdrant Dense Search
        query_vec = embedding_service.embed_text("security controls")
        dense_hits = isolated_dual_indexer.dense_indexer.vector_store_service.search_vectors(query_vector=query_vec)
        assert len(dense_hits) == 1
        assert dense_hits[0].chunk_id == c1.id

        # Verify BM25 Sparse Search
        bm25_hits = isolated_dual_indexer.sparse_indexer.search("ISO-27001")
        assert len(bm25_hits) == 1
        assert bm25_hits[0].chunk_id == c1.id

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_dual_indexing_service_partial_failure_reporting(isolated_dual_indexer):
    """
    Verifies that if sparse indexing encounters an exception, success=False is reported.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = uuid.uuid4()

    async with test_async_session() as session:
        doc = Document(
            id=doc_id,
            title="Failure Test Doc",
            file_path="/tmp/fail.pdf",
            file_hash="hash_fail",
            file_type="pdf",
        )
        session.add(doc)

        c1 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="Sample text content for failure test.",
            token_count=8,
        )
        session.add(c1)
        await session.commit()

        # Mock sparse indexer to simulate failure
        isolated_dual_indexer.sparse_indexer.index_chunks = MagicMock(
            side_effect=Exception("Simulated BM25 disk error")
        )

        result = await isolated_dual_indexer.index_document(document_id=doc_id, version_id=None, db=session)

        assert result.success is False
        assert "Simulated BM25 disk error" in result.error

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_dual_indexing_deterministic_recovery(isolated_dual_indexer):
    """
    Verifies that calling reindex_document cleans up existing state and rebuilds cleanly.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = uuid.uuid4()

    async with test_async_session() as session:
        doc = Document(
            id=doc_id,
            title="Recovery Test Doc",
            file_path="/tmp/rec.pdf",
            file_hash="hash_rec",
            file_type="pdf",
        )
        session.add(doc)

        c1 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="Initial text content.",
            token_count=5,
        )
        session.add(c1)
        await session.commit()

        # Initial indexing
        res1 = await isolated_dual_indexer.index_document(document_id=doc_id, version_id=None, db=session)
        assert res1.success is True

        # Re-index
        res2 = await isolated_dual_indexer.reindex_document(document_id=doc_id, version_id=None, db=session)
        assert res2.success is True
        assert res2.dense_indexed_count == 1
        assert res2.sparse_indexed_count == 1

    await test_async_engine.dispose()
