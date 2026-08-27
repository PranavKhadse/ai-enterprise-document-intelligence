"""
Document ingestion and upload API endpoints.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.document import Document
from backend.app.db.session import get_db
from backend.app.schemas.document import DocumentUploadResponse
from backend.app.services.storage import (
    FileSizeExceededError,
    InvalidFileTypeError,
    storage_service,
)

router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload & Ingest PDF Document",
    description=(
        "Accepts an enterprise PDF document, validates size and signature, computes SHA-256 hash, "
        "stores the original file, and creates a Document record."
    ),
)
async def upload_document(
    response: Response,
    file: UploadFile = File(..., description="PDF document file to upload"),
    department_id: Optional[uuid.UUID] = Form(None, description="Optional associated Department UUID"),
    title: Optional[str] = Form(None, description="Optional custom title (defaults to filename)"),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """
    Secure document ingestion endpoint:
    1. Validates file extension and magic bytes (%PDF-).
    2. Streams file safely to disk while enforcing MAX_UPLOAD_SIZE_BYTES.
    3. Computes SHA-256 content hash.
    4. Handles duplicates: Returns existing record if duplicate hash found.
    5. Persists Document ORM record and returns structured metadata.

    NOTE on Concurrent Deduplication:
    Currently, deduplication is performed by querying Document.file_hash prior to insertion.
    True atomic concurrency deduplication across high-throughput distributed workers will
    require an explicit database-level UNIQUE constraint on documents.file_hash in a future migration.
    """
    file_path: Optional[str] = None
    try:
        file_path, file_hash = await storage_service.save_file(file)
    except InvalidFileTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileSizeExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and store uploaded file: {str(e)}",
        )

    # Check for duplicate document via SHA-256 hash
    stmt = select(Document).where(Document.file_hash == file_hash)
    result = await db.execute(stmt)
    existing_doc = result.scalars().first()

    if existing_doc:
        # Avoid storing duplicate binary copies on disk
        if file_path:
            storage_service.delete_file(file_path)

        # Set HTTP 200 OK for duplicate/already-existing resource
        response.status_code = status.HTTP_200_OK

        return DocumentUploadResponse(
            id=existing_doc.id,
            title=existing_doc.title,
            file_hash=existing_doc.file_hash,
            file_type=existing_doc.file_type,
            status="already_exists",
            is_duplicate=True,
            department_id=existing_doc.department_id,
            current_version=existing_doc.current_version,
            created_at=existing_doc.created_at,
        )

    # Document is new: persist ORM record
    doc_title = title.strip() if title and title.strip() else (file.filename or "Untitled Document")
    new_doc = Document(
        title=doc_title,
        file_path=file_path,
        file_hash=file_hash,
        file_type="pdf",
        department_id=department_id,
        current_version="1.0.0",
    )

    try:
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)
    except Exception as db_err:
        await db.rollback()
        # Clean up file on disk if database persistence fails
        if file_path:
            storage_service.delete_file(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed: {str(db_err)}",
        )

    # Record document creation audit event
    from backend.app.schemas.audit import AuditEventType
    from backend.app.services.audit_service import audit_service
    await audit_service.record_document_event(
        event_type=AuditEventType.DOCUMENT_CREATED,
        action="upload_pdf_document",
        document_id=str(new_doc.id),
        title=new_doc.title,
        file_hash=new_doc.file_hash,
        department_id=str(new_doc.department_id) if new_doc.department_id else None,
        db=db,
    )

    return DocumentUploadResponse(
        id=new_doc.id,
        title=new_doc.title,
        file_hash=new_doc.file_hash,
        file_type=new_doc.file_type,
        status="uploaded",
        is_duplicate=False,
        department_id=new_doc.department_id,
        current_version=new_doc.current_version,
        created_at=new_doc.created_at,
    )
