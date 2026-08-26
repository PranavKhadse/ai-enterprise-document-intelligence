"""
Qdrant Vector Database Integration Service.
Manages collections with Cosine distance and HNSW indexing, dimension validation,
idempotent point upserts, payload querying, and version-isolated deletion.
"""
import uuid
from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    HnswConfigDiff,
    MatchValue,
    PointStruct,
    VectorParams,
)
from backend.app.core.config import settings
from backend.app.schemas.embedding import VectorSearchResult


class VectorStoreError(Exception):
    """Base exception for vector database operations."""
    pass


class VectorDimensionMismatchError(VectorStoreError):
    """Raised when collection vector dimension differs from the configured embedding model."""
    pass


class CollectionNotFoundError(VectorStoreError):
    """Raised when targeted Qdrant collection does not exist."""
    pass


class VectorStoreService:
    """
    Service wrapping Qdrant client with dimension compatibility checks and filtering.
    """

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        collection_name: Optional[str] = None,
    ):
        self._client = client
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            try:
                self._client = QdrantClient(
                    url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
                    api_key=settings.QDRANT_API_KEY,
                    timeout=10.0,
                )
            except Exception as e:
                raise VectorStoreError(f"Failed to connect to Qdrant server: {str(e)}")
        return self._client

    def ensure_collection(self, dimension: Optional[int] = None) -> None:
        """
        Creates or validates the Qdrant collection with Cosine similarity and HNSW config.
        Fails fast if the existing collection's vector dimension does not match the target dimension.
        """
        client = self._get_client()
        target_dim = dimension or settings.EMBEDDING_DIMENSION

        try:
            exists = client.collection_exists(collection_name=self.collection_name)
            if exists:
                collection_info = client.get_collection(collection_name=self.collection_name)
                # Inspect existing vector dimension
                existing_params = collection_info.config.params.vectors
                if isinstance(existing_params, VectorParams):
                    existing_dim = existing_params.size
                    if existing_dim != target_dim:
                        raise VectorDimensionMismatchError(
                            f"Qdrant collection '{self.collection_name}' has vector dimension {existing_dim}, "
                            f"but configured embedding dimension is {target_dim}."
                        )
                return

            # Create new collection
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=target_dim, distance=Distance.COSINE),
                hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            )
        except VectorDimensionMismatchError:
            raise
        except Exception as e:
            raise VectorStoreError(f"Failed to ensure Qdrant collection '{self.collection_name}': {str(e)}")

    def upsert_points(self, points: List[PointStruct], dimension: Optional[int] = None) -> None:
        """
        Idempotently upserts points into Qdrant in batches.
        """
        if not points:
            return

        self.ensure_collection(dimension=dimension)
        client = self._get_client()

        try:
            client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to upsert points into Qdrant: {str(e)}")

    def search_vectors(
        self,
        query_vector: List[float],
        limit: int = 10,
        document_id: Optional[uuid.UUID] = None,
        version_id: Optional[uuid.UUID] = None,
        department_id: Optional[uuid.UUID] = None,
    ) -> List[VectorSearchResult]:
        """
        Executes a vector similarity search with optional payload pre-filtering.
        """
        client = self._get_client()
        must_conditions: List[FieldCondition] = []

        if document_id:
            must_conditions.append(
                FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))
            )
        if version_id:
            must_conditions.append(
                FieldCondition(key="version_id", match=MatchValue(value=str(version_id)))
            )
        if department_id:
            must_conditions.append(
                FieldCondition(key="department_id", match=MatchValue(value=str(department_id)))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        try:
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                hits = response.points
            elif hasattr(client, "search"):
                hits = client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
            else:
                raise VectorStoreError("QdrantClient does not support query_points or search.")
        except Exception as e:
            raise VectorStoreError(f"Vector search failed: {str(e)}")

        results: List[VectorSearchResult] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                VectorSearchResult(
                    chunk_id=uuid.UUID(str(hit.id)),
                    document_id=uuid.UUID(payload.get("document_id", str(uuid.uuid4()))),
                    version_id=uuid.UUID(payload["version_id"]) if payload.get("version_id") else None,
                    score=float(hit.score),
                    content=payload.get("content", ""),
                    page_number=payload.get("page_number"),
                    section_path=payload.get("section_path"),
                    payload=payload,
                )
            )

        return results

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        """
        Deletes all vector points associated with a specific document.
        """
        client = self._get_client()
        try:
            client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to delete vectors for document {document_id}: {str(e)}")

    def delete_by_version(self, document_id: uuid.UUID, version_id: Optional[uuid.UUID]) -> None:
        """
        Deletes all vector points associated with a specific document version.
        """
        client = self._get_client()
        must_conds = [
            FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))
        ]
        if version_id:
            must_conds.append(
                FieldCondition(key="version_id", match=MatchValue(value=str(version_id)))
            )

        try:
            client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(filter=Filter(must=must_conds)),
                wait=True,
            )
        except Exception as e:
            raise VectorStoreError(
                f"Failed to delete vectors for document {document_id} version {version_id}: {str(e)}"
            )


# Global vector store service singleton
vector_store_service = VectorStoreService()
