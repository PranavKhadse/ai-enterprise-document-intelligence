"""
Pydantic schemas for Dense Embeddings, Vector Store Search, and Document Indexing.
"""
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class EmbeddingConfig(BaseModel):
    """
    Configuration parameters for dense embedding generation.
    """
    provider: str = Field(default="fastembed", description="Embedding engine provider (fastembed, etc.)")
    model_name: str = Field(default="BAAI/bge-small-en-v1.5", description="Model identifier")
    dimension: int = Field(default=384, description="Output embedding vector dimension")
    batch_size: int = Field(default=32, description="Batch size for vector inference")

    model_config = ConfigDict(from_attributes=True)


class VectorSearchResult(BaseModel):
    """
    Structured result returned from a Qdrant vector similarity search.
    """
    chunk_id: uuid.UUID = Field(..., description="Matching DocumentChunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional DocumentVersion UUID")
    score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    content: str = Field(..., description="Chunk content text with breadcrumbs")
    page_number: Optional[int] = Field(None, description="Primary starting page number")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Full Qdrant payload dictionary")

    model_config = ConfigDict(from_attributes=True)


class IndexingResult(BaseModel):
    """
    Structured result returned after indexing a document's chunks into Qdrant.
    """
    success: bool = Field(..., description="Whether the indexing operation completed without error")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional DocumentVersion UUID")
    indexed_count: int = Field(default=0, description="Total number of chunks successfully embedded and upserted")
    vector_dimension: int = Field(..., description="Vector dimension of indexed embeddings")
    error: Optional[str] = Field(None, description="Error message if indexing failed")

    model_config = ConfigDict(from_attributes=True)
