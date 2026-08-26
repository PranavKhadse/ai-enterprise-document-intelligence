"""
Dual Indexing Orchestration Service.
Coordinates unified ingestion across Qdrant (dense vectors) and BM25 (sparse inverted index)
with deterministic re-indexing and failure recovery.
"""
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.bm25 import DualIndexingResult
from backend.app.services.bm25 import BM25IndexService, bm25_service
from backend.app.services.indexer import IndexingService, indexing_service


class DualIndexingService:
    """
    Unified dual-indexing orchestrator for dense vector and sparse lexical retrieval.
    """

    def __init__(
        self,
        dense_indexer: Optional[IndexingService] = None,
        sparse_indexer: Optional[BM25IndexService] = None,
    ):
        self.dense_indexer = dense_indexer or indexing_service
        self.sparse_indexer = sparse_indexer or bm25_service

    async def index_document(
        self,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> DualIndexingResult:
        """
        Indexes a document's chunks into both Qdrant and BM25 in a single unified operation.
        """
        if db is None:
            return DualIndexingResult(
                success=False,
                document_id=document_id,
                version_id=version_id,
                dense_indexed_count=0,
                sparse_indexed_count=0,
                vector_dimension=settings.EMBEDDING_DIMENSION,
                error="AsyncSession 'db' must be provided for dual indexing.",
            )

        try:
            # 1. Fetch parent document
            doc_stmt = select(Document).where(Document.id == document_id)
            doc_result = await db.execute(doc_stmt)
            document = doc_result.scalars().first()

            if not document:
                return DualIndexingResult(
                    success=False,
                    document_id=document_id,
                    version_id=version_id,
                    dense_indexed_count=0,
                    sparse_indexed_count=0,
                    vector_dimension=settings.EMBEDDING_DIMENSION,
                    error=f"Document with ID {document_id} not found in database.",
                )

            # 2. Fetch chunks
            if version_id is None:
                chunk_stmt = (
                    select(DocumentChunk)
                    .where(
                        DocumentChunk.document_id == document_id,
                        DocumentChunk.version_id.is_(None),
                    )
                    .order_by(DocumentChunk.chunk_index.asc())
                )
            else:
                chunk_stmt = (
                    select(DocumentChunk)
                    .where(
                        DocumentChunk.document_id == document_id,
                        DocumentChunk.version_id == version_id,
                    )
                    .order_by(DocumentChunk.chunk_index.asc())
                )

            chunk_result = await db.execute(chunk_stmt)
            chunks = chunk_result.scalars().all()

            if not chunks:
                return DualIndexingResult(
                    success=True,
                    document_id=document_id,
                    version_id=version_id,
                    dense_indexed_count=0,
                    sparse_indexed_count=0,
                    vector_dimension=settings.EMBEDDING_DIMENSION,
                )

            # 3. Dense Vector Indexing (Qdrant)
            dense_res = await self.dense_indexer.index_document(
                document_id=document_id,
                version_id=version_id,
                db=db,
            )

            if not dense_res.success:
                return DualIndexingResult(
                    success=False,
                    document_id=document_id,
                    version_id=version_id,
                    dense_indexed_count=0,
                    sparse_indexed_count=0,
                    vector_dimension=dense_res.vector_dimension,
                    error=f"Dense indexing failed: {dense_res.error}",
                )

            # 4. Sparse Lexical Indexing (BM25 with operation-level persistence)
            try:
                sparse_count = self.sparse_indexer.index_chunks(
                    chunks=chunks,
                    document=document,
                )
            except Exception as e:
                return DualIndexingResult(
                    success=False,
                    document_id=document_id,
                    version_id=version_id,
                    dense_indexed_count=dense_res.indexed_count,
                    sparse_indexed_count=0,
                    vector_dimension=dense_res.vector_dimension,
                    error=f"Sparse lexical indexing failed: {str(e)}",
                )

            return DualIndexingResult(
                success=True,
                document_id=document_id,
                version_id=version_id,
                dense_indexed_count=dense_res.indexed_count,
                sparse_indexed_count=sparse_count,
                vector_dimension=dense_res.vector_dimension,
            )

        except Exception as e:
            return DualIndexingResult(
                success=False,
                document_id=document_id,
                version_id=version_id,
                dense_indexed_count=0,
                sparse_indexed_count=0,
                vector_dimension=settings.EMBEDDING_DIMENSION,
                error=str(e),
            )

    async def delete_document_index(
        self,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID] = None,
    ) -> None:
        """
        Deletes vector points from Qdrant and inverted postings from BM25.
        """
        if version_id is not None:
            self.dense_indexer.vector_store_service.delete_by_version(document_id, version_id)
            self.sparse_indexer.delete_by_version(document_id, version_id)
        else:
            self.dense_indexer.vector_store_service.delete_by_document(document_id)
            self.sparse_indexer.delete_by_document(document_id)

    async def reindex_document(
        self,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> DualIndexingResult:
        """
        Deterministically recovers from partial failures by purging and rebuilding
        both dense and sparse indices from the PostgreSQL source of truth.
        """
        return await self.index_document(document_id=document_id, version_id=version_id, db=db)


# Global dual indexing service singleton
dual_indexing_service = DualIndexingService()
