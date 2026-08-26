"""
Pydantic schemas for Structure-Aware Chunking & Metadata Enrichment.
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


class ChunkMetadata(BaseModel):
    """
    JSON-serializable metadata stored inside DocumentChunk.metadata_json.
    """
    document_title: Optional[str] = Field(None, description="Title of the source document")
    section_path: Optional[str] = Field(None, description="Hierarchical section breadcrumb path")
    primary_page: Optional[int] = Field(None, description="Primary/starting 1-indexed page number")
    page_numbers: List[int] = Field(default_factory=list, description="All contributing 1-indexed page numbers")
    element_types: List[str] = Field(default_factory=list, description="Types of structural elements in this chunk")
    source_element_ids: List[str] = Field(default_factory=list, description="IDs of source parsed elements")
    bounding_boxes: List[Tuple[float, float, float, float]] = Field(
        default_factory=list, description="Bounding boxes of elements contributing to the chunk"
    )
    token_count: int = Field(..., description="Actual token count of the final chunk content")
    char_count: int = Field(..., description="Character count of the final chunk content")
    is_table: bool = Field(False, description="Whether this chunk represents tabular data")
    chunk_hash: str = Field(..., description="Deterministic SHA-256 hash of canonical chunk string")

    model_config = ConfigDict(from_attributes=True)


class ChunkingConfig(BaseModel):
    """
    Configuration parameters for structure-aware chunk generation.
    """
    target_size_tokens: int = Field(default=450, ge=50, le=512, description="Target token budget per chunk")
    max_size_tokens: int = Field(default=512, ge=50, le=512, description="Strict hard token ceiling per chunk")
    overlap_tokens: int = Field(default=50, ge=0, le=100, description="Token overlap between adjacent text chunks")
    tokenizer_encoding: str = Field(default="cl100k_base", description="Tiktoken encoding name")
    include_breadcrumbs: bool = Field(default=True, description="Whether to prepend context breadcrumbs to content")

    model_config = ConfigDict(from_attributes=True)


class ChunkDTO(BaseModel):
    """
    In-memory data transfer object for a generated chunk before/after DB persistence.
    """
    document_id: uuid.UUID = Field(..., description="Parent document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional document version UUID")
    chunk_index: int = Field(..., description="0-indexed sequence position of the chunk")
    content: str = Field(..., description="Final breadcrumb-injected chunk content")
    page_number: Optional[int] = Field(None, description="Primary/starting page number")
    section_path: Optional[str] = Field(None, description="Section breadcrumb path")
    token_count: int = Field(..., description="Token count of final content")
    metadata: ChunkMetadata = Field(..., description="Enriched metadata payload")

    model_config = ConfigDict(from_attributes=True)


class DocumentChunksResponse(BaseModel):
    """
    Response schema for listing document chunks.
    """
    document_id: uuid.UUID = Field(..., description="Parent document UUID")
    version_id: Optional[uuid.UUID] = Field(None, description="Optional document version UUID")
    total_chunks: int = Field(..., description="Total number of chunks generated for this document")
    chunks: List[ChunkDTO] = Field(default_factory=list, description="List of generated chunks")

    model_config = ConfigDict(from_attributes=True)
