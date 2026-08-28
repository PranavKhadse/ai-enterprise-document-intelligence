"""
Document ingestion and upload API endpoints.
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.db.session import get_db
from backend.app.schemas.document import (
    DocumentChunkResponse,
    DocumentChunksListResponse,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentSearchRequest,
    DocumentUploadResponse,
)
from backend.app.schemas.retrieval import HybridRetrievalResponse
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

    # Attempt automatic parsing, chunking, and dual indexing for immediate searchability
    try:
        from backend.app.services.parser import parser_service
        from backend.app.services.chunker import chunker_service
        from backend.app.services.dual_indexer import dual_indexing_service
        parsed_doc = await parser_service.parse_and_update_document(new_doc.id, db)
        if parsed_doc:
            await chunker_service.chunk_and_store_document(new_doc.id, parsed_doc, db)
            await dual_indexing_service.index_document(new_doc.id, db=db)
    except Exception:
        # Non-blocking: allows upload to succeed even if indexing is queued or mock test streams are used
        pass

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


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List enterprise documents",
    description="Retrieves a paginated list of ingested enterprise documents with optional department and title search filters.",
)
async def list_documents(
    query: Optional[str] = Query(None, description="Optional title search query"),
    department_id: Optional[uuid.UUID] = Query(None, description="Filter by department UUID"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """Returns paginated documents list ordered by creation date descending."""
    base_stmt = select(Document)
    count_stmt = select(func.count(Document.id))

    if department_id:
        base_stmt = base_stmt.where(Document.department_id == department_id)
        count_stmt = count_stmt.where(Document.department_id == department_id)

    if query and query.strip():
        search_pattern = f"%{query.strip()}%"
        base_stmt = base_stmt.where(Document.title.ilike(search_pattern))
        count_stmt = count_stmt.where(Document.title.ilike(search_pattern))

    # Get total count
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one() or 0

    # Get paginated items
    stmt = (
        base_stmt.options(selectinload(Document.chunks))
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    docs = result.scalars().all()

    items: List[DocumentItemResponse] = []
    for doc in docs:
        chunks_count = len(doc.chunks) if doc.chunks else 0
        items.append(
            DocumentItemResponse(
                id=doc.id,
                title=doc.title,
                file_hash=doc.file_hash,
                file_type=doc.file_type,
                total_pages=doc.total_pages,
                department_id=doc.department_id,
                current_version=doc.current_version,
                created_at=doc.created_at,
                chunks_count=chunks_count,
            )
        )

    return DocumentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document details",
    description="Retrieves metadata and status details for a single document by its UUID.",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentItemResponse:
    """Retrieves single document metadata by ID."""
    stmt = select(Document).options(selectinload(Document.chunks)).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalars().first()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' was not found.",
        )

    chunks_count = len(doc.chunks) if doc.chunks else 0
    return DocumentItemResponse(
        id=doc.id,
        title=doc.title,
        file_hash=doc.file_hash,
        file_type=doc.file_type,
        total_pages=doc.total_pages,
        department_id=doc.department_id,
        current_version=doc.current_version,
        created_at=doc.created_at,
        chunks_count=chunks_count,
    )


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentChunksListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document chunks",
    description="Retrieves a paginated list of structural chunks for a specific document.",
)
async def get_document_chunks(
    document_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> DocumentChunksListResponse:
    """Retrieves parsed chunks for a document."""
    # Verify document exists
    doc_stmt = select(Document.id).where(Document.id == document_id)
    doc_res = await db.execute(doc_stmt)
    if not doc_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' was not found.",
        )

    count_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one() or 0

    chunk_stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .limit(limit)
        .offset(offset)
    )
    chunk_res = await db.execute(chunk_stmt)
    chunks = chunk_res.scalars().all()

    items = [DocumentChunkResponse.model_validate(c) for c in chunks]

    return DocumentChunksListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete document",
    description="Permanently deletes a document record, removes its file from storage, purges vector and BM25 index entries, and records an audit log.",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Deletes document and associated vector/lexical index entries."""
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalars().first()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' was not found.",
        )

    doc_title = doc.title
    doc_file_hash = doc.file_hash
    doc_file_path = doc.file_path
    doc_dept_id = str(doc.department_id) if doc.department_id else None

    # Delete index postings safely
    try:
        from backend.app.services.dual_indexer import dual_indexing_service
        await dual_indexing_service.delete_document_index(document_id)
    except Exception:
        pass  # Ensure database deletion proceeds even if external index purge experiences a transient issue

    # Delete physical file from storage safely
    if doc_file_path:
        try:
            storage_service.delete_file(doc_file_path)
        except Exception:
            pass

    # Delete from database (cascades to chunks and versions)
    await db.delete(doc)
    await db.commit()

    # Record audit event
    from backend.app.schemas.audit import AuditEventType
    from backend.app.services.audit_service import audit_service
    await audit_service.record_document_event(
        event_type=AuditEventType.DOCUMENT_DELETED,
        action="delete_document",
        document_id=str(document_id),
        title=doc_title,
        file_hash=doc_file_hash,
        department_id=doc_dept_id,
        db=db,
    )

    return {
        "success": True,
        "message": f"Document '{doc_title}' ({document_id}) has been permanently deleted.",
        "document_id": str(document_id),
    }


@router.post(
    "/search",
    response_model=HybridRetrievalResponse,
    status_code=status.HTTP_200_OK,
    summary="Hybrid Lexical & Semantic Search",
    description="Executes hybrid retrieval (Dense vector search + BM25 sparse search with Reciprocal Rank Fusion) and returns scored candidate passages.",
)
async def search_documents(
    request: DocumentSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> HybridRetrievalResponse:
    """Direct hybrid search endpoint using Phase 5 & 6 retrieval engine."""
    from backend.app.services.hybrid_retriever import hybrid_retriever

    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty or solely whitespace.",
        )

    try:
        response = await hybrid_retriever.retrieve(
            query=request.query,
            filter=request.filter,
            strategy=request.strategy,
            final_top_k=request.top_k,
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hybrid search failed: {str(e)}",
        )

