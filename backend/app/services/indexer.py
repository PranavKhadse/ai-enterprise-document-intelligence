"""
Document Indexing Orchestration Service.
Coordinates loading chunks from PostgreSQL, generating dense embeddings,
and idempotently upserting points with rich metadata into Qdrant.
"""
import uuid
from typing import Optional
from qdrant_client.http.models import PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.embedding import IndexingResult
from backend.app.services.embedding import EmbeddingService, embedding_service
from backend.app.services.vector_store import VectorStoreService, vector_store_service


class IndexingService:
    """
    Orchestrates the indexing flow: PostgreSQL -> Embeddings -> Qdrant.
    """

    def __init__(
        self,
        embed_service: Optional[EmbeddingService] = None,
        store_service: Optional[VectorStoreService] = None,
    ):
        self.embedding_service = embed_service or embedding_service
        self.vector_store_service = store_service or vector_store_service

    async def index_document(
        self,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> IndexingResult:
        """
        Indexes a document's chunks into Qdrant.
        Idempotently overwrites existing vectors for the same chunks.
        """
        if db is None:
            return IndexingResult(
                success=False,
                document_id=document_id,
                version_id=version_id,
                indexed_count=0,
                vector_dimension=self.embedding_service.dimension,
                error="AsyncSession 'db' must be provided for document indexing.",
            )

        try:
            # 1. Fetch parent document
            doc_stmt = select(Document).where(Document.id == document_id)
            doc_result = await db.execute(doc_stmt)
            document = doc_result.scalars().first()

            if not document:
                return IndexingResult(
                    success=False,
                    document_id=document_id,
                    version_id=version_id,
                    indexed_count=0,
                    vector_dimension=self.embedding_service.dimension,
                    error=f"Document with ID {document_id} not found in database.",
                )

            # 2. Fetch chunks for (document_id, version_id)
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

            # 3. Handle empty chunk list gracefully
            if not chunks:
                return IndexingResult(
                    success=True,
                    document_id=document_id,
                    version_id=version_id,
                    indexed_count=0,
                    vector_dimension=self.embedding_service.dimension,
                )

            # 4. Pre-flight check / ensure Qdrant collection compatibility
            self.vector_store_service.ensure_collection(dimension=self.embedding_service.dimension)

            # 5. Batch generate normalized embeddings
            texts = [c.content for c in chunks]
            vectors = self.embedding_service.embed_batch(texts)

            # 6. Build Qdrant PointStruct objects with rich payload
            points = []
            for chunk, vector in zip(chunks, vectors):
                meta = chunk.metadata_json or {}
                payload = {
                    "document_id": str(document.id),
                    "version_id": str(version_id) if version_id else None,
                    "chunk_id": str(chunk.id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "page_numbers": meta.get("page_numbers", [chunk.page_number] if chunk.page_number else []),
                    "section_path": chunk.section_path,
                    "document_title": document.title,
                    "department_id": str(document.department_id) if document.department_id else None,
                    "is_table": meta.get("is_table", False),
                    "token_count": chunk.token_count,
                }
                points.append(
                    PointStruct(
                        id=str(chunk.id),
                        vector=vector,
                        payload=payload,
                    )
                )

            # 7. Idempotently upsert points into Qdrant
            self.vector_store_service.upsert_points(points, dimension=self.embedding_service.dimension)

            return IndexingResult(
                success=True,
                document_id=document_id,
                version_id=version_id,
                indexed_count=len(points),
                vector_dimension=self.embedding_service.dimension,
            )

        except Exception as e:
            return IndexingResult(
                success=False,
                document_id=document_id,
                version_id=version_id,
                indexed_count=0,
                vector_dimension=self.embedding_service.dimension,
                error=str(e),
            )


# Global indexing service singleton
indexing_service = IndexingService()
