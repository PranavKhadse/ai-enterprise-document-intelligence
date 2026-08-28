"""
Pydantic schemas for Document operations and ingestion.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.retrieval import FusionStrategy, RetrievalFilter


class DocumentUploadResponse(BaseModel):
    """
    Response schema for document upload operation.
    """
    id: uuid.UUID = Field(..., description="Unique document UUID")
    title: str = Field(..., description="Original filename or document title")
    file_hash: str = Field(..., description="SHA-256 content hash")
    file_type: str = Field(..., description="Document format extension (e.g., pdf)")
    status: str = Field(..., description="Upload status: 'uploaded' or 'already_exists'")
    is_duplicate: bool = Field(..., description="Whether an identical document already existed")
    department_id: Optional[uuid.UUID] = Field(None, description="Associated department ID if provided")
    current_version: str = Field(..., description="Current active version of the document")
    created_at: datetime = Field(..., description="UTC creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class DocumentItemResponse(BaseModel):
    """
    Detailed read model DTO for a document in repository listings.
    """
    id: uuid.UUID
    title: str
    file_hash: str
    file_type: str
    total_pages: Optional[int] = None
    department_id: Optional[uuid.UUID] = None
    current_version: str
    created_at: datetime
    chunks_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """
    Paginated collection response for enterprise documents.
    """
    items: List[DocumentItemResponse] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total matching documents count")
    limit: int = Field(ge=1, le=100, description="Pagination size limit")
    offset: int = Field(ge=0, description="Pagination offset")

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkResponse(BaseModel):
    """
    Structured passage chunk representation for document explorer.
    """
    id: uuid.UUID
    document_id: uuid.UUID
    version_id: Optional[uuid.UUID] = None
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    section_path: Optional[str] = None
    token_count: Optional[int] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class DocumentChunksListResponse(BaseModel):
    """
    Paginated collection response for document chunks.
    """
    items: List[DocumentChunkResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class DocumentSearchRequest(BaseModel):
    """
    Request model for hybrid lexical & semantic search.
    """
    query: str = Field(..., min_length=1, max_length=2000, description="Search query string")
    filter: Optional[RetrievalFilter] = Field(None, description="Optional metadata/RBAC filters")
    strategy: Optional[FusionStrategy] = Field(None, description="Optional fusion strategy override")
    top_k: Optional[int] = Field(default=10, ge=1, le=50, description="Number of results to retrieve")

    model_config = ConfigDict(from_attributes=True)

