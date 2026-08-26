"""
Pydantic schemas for Document operations and ingestion.
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


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
