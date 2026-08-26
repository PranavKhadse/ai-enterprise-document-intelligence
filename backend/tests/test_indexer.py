"""
End-to-end integration tests for Document Indexing Service.
"""
import uuid
from unittest.mock import MagicMock
import pytest
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models import Department, Document, DocumentChunk
from backend.app.schemas.embedding import IndexingResult
from backend.app.services.embedding import embedding_service
from backend.app.services.indexer import IndexingService
from backend.app.services.vector_store import VectorStoreError, VectorStoreService


@pytest.fixture
def in_memory_vector_service():
    client = QdrantClient(location=":memory:")
    return VectorStoreService(client=client, collection_name="test_indexing_collection")


@pytest.mark.asyncio
async def test_end_to_end_indexing_service(in_memory_vector_service):
    """
    Test full flow: PostgreSQL Document + Chunks -> IndexingService -> Qdrant.
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
        dept = Department(id=dept_id, name="Human Resources")
        session.add(dept)

        doc = Document(
            id=doc_id,
            title="Leave Guidelines 2026",
            file_path="/tmp/leave.pdf",
            file_hash="hash_123",
            file_type="pdf",
            department_id=dept_id,
        )
        session.add(doc)

        c1 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="[Context: Leave Guidelines] Maternity leave is 26 weeks.",
            page_number=1,
            section_path="Guidelines > Maternity",
            metadata_json={"page_numbers": [1], "is_table": False},
            token_count=12,
        )
        c2 = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=1,
            content="[Context: Leave Guidelines] Paternity leave is 4 weeks.",
            page_number=2,
            section_path="Guidelines > Paternity",
            metadata_json={"page_numbers": [2], "is_table": False},
            token_count=12,
        )
        session.add_all([c1, c2])
        await session.commit()

        # Execute Indexing Service
        indexer = IndexingService(
            embed_service=embedding_service,
            store_service=in_memory_vector_service,
        )

        result = await indexer.index_document(document_id=doc_id, version_id=None, db=session)

        assert isinstance(result, IndexingResult)
        assert result.success is True
        assert result.indexed_count == 2
        assert result.vector_dimension == 384
        assert result.error is None

        # Verify Qdrant points
        query_vec = embedding_service.embed_text("maternity leave duration")
        search_results = in_memory_vector_service.search_vectors(query_vector=query_vec, limit=2)

        assert len(search_results) == 2
        assert "Maternity leave is 26 weeks" in search_results[0].content
        assert search_results[0].payload["department_id"] == str(dept_id)

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_empty_document_chunk_list_handling(in_memory_vector_service):
    """
    Verifies that indexing a document with 0 chunks returns success=True, indexed_count=0 without error.
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
            title="Empty Document",
            file_path="/tmp/empty.pdf",
            file_hash="hash_empty",
            file_type="pdf",
        )
        session.add(doc)
        await session.commit()

        indexer = IndexingService(
            embed_service=embedding_service,
            store_service=in_memory_vector_service,
        )

        result = await indexer.index_document(document_id=doc_id, version_id=None, db=session)
        assert result.success is True
        assert result.indexed_count == 0
        assert result.error is None

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_failed_indexing_nonexistent_document(in_memory_vector_service):
    """
    Verifies that indexing a non-existent document ID returns success=False with clear error.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_async_session() as session:
        indexer = IndexingService(
            embed_service=embedding_service,
            store_service=in_memory_vector_service,
        )

        fake_id = uuid.uuid4()
        result = await indexer.index_document(document_id=fake_id, version_id=None, db=session)

        assert result.success is False
        assert result.indexed_count == 0
        assert "not found" in result.error

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_partial_indexing_upsert_failure_handling(in_memory_vector_service):
    """
    Verifies that when Qdrant upsert raises an error, indexing returns success=False
    and reports the failure without corrupting database state.
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
            title="Sample Failure Document",
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
            page_number=1,
            section_path="Section > Fail",
            metadata_json={"page_numbers": [1], "is_table": False},
            token_count=10,
        )
        session.add(c1)
        await session.commit()

        # Mock vector store service to raise an exception during upsert
        mock_store_service = MagicMock(spec=VectorStoreService)
        mock_store_service.ensure_collection.return_value = None
        mock_store_service.upsert_points.side_effect = VectorStoreError("Simulated Qdrant network outage")

        indexer = IndexingService(
            embed_service=embedding_service,
            store_service=mock_store_service,
        )

        result = await indexer.index_document(document_id=doc_id, version_id=None, db=session)

        # Must report failure cleanly
        assert result.success is False
        assert result.indexed_count == 0
        assert "Simulated Qdrant network outage" in result.error

    await test_async_engine.dispose()
