"""
Pydantic schemas for BM25 Sparse Lexical Search and Dual Indexing.
"""
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BM25Config(BaseModel):
    """
    Configuration parameters for BM25Okapi scoring and persistence.
    """
    k1: float = Field(default=1.5, ge=0.0, description="Term frequency saturation parameter")
    b: float = Field(default=0.75, ge=0.0, le=1.0, description="Document length normalization parameter")
    index_path: str = Field(default="data/bm25_index.pkl", description="Filepath for atomic disk persistence")
    auto_persist: bool = Field(default=True, description="Whether to atomically persist index after document indexing")
    min_token_length: int = Field(default=1, ge=1, description="Minimum length of indexed tokens")

    model_config = ConfigDict(from_attributes=True)


class BM25SearchResult(BaseModel):
    """
    Structured result returned from a BM25 sparse lexical search query.
    """
    chunk_id: uuid.UUID = Field(..., description="Matching DocumentChunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional DocumentVersion UUID")
    score: float = Field(..., description="BM25 relevance score")
    content: str = Field(..., description="Chunk content text with breadcrumbs")
    page_number: Optional[int] = Field(None, description="Primary starting page number")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")

    model_config = ConfigDict(from_attributes=True)


class DualIndexingResult(BaseModel):
    """
    Unified result returned after dual-indexing a document into both Qdrant and BM25.
    """
    success: bool = Field(..., description="Whether both dense and sparse indexing completed successfully")
    document_id: uuid.UUID = Field(..., description="Parent Document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional DocumentVersion UUID")
    dense_indexed_count: int = Field(default=0, description="Number of vectors indexed in Qdrant")
    sparse_indexed_count: int = Field(default=0, description="Number of chunks indexed in BM25")
    vector_dimension: int = Field(..., description="Dense vector dimension")
    error: Optional[str] = Field(None, description="Detailed error message if dual indexing failed")

    model_config = ConfigDict(from_attributes=True)
