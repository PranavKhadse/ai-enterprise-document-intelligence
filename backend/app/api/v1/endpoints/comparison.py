"""
Document Comparison & Policy Conflict Intelligence Endpoints.
Provides REST APIs for comparing document versions, diffing clauses, and detecting policy contradictions.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.session import get_db
from backend.app.schemas.comparison import (
    DocumentComparisonRequest,
    DocumentComparisonResponse,
)
from backend.app.services.document_comparator import document_comparator

router = APIRouter()


@router.post(
    "/compare",
    response_model=DocumentComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare two enterprise documents or versions",
    description="Extracts, aligns, and compares clauses between two documents, identifying policy contradictions and entity variances.",
)
async def compare_documents(
    request: DocumentComparisonRequest,
    db: AsyncSession = Depends(get_db),
) -> DocumentComparisonResponse:
    """
    Compares two documents either by database UUID or by ad-hoc raw text/markdown.
    """
    try:
        response = await document_comparator.compare_documents(request, db=db)
        # Record Phase 11 document comparison audit event
        from backend.app.services.audit_service import audit_service
        doc_a_str = str(request.document_a_id) if request.document_a_id else "raw_text_a"
        doc_b_str = str(request.document_b_id) if request.document_b_id else "raw_text_b"
        await audit_service.record_comparison_event(
            doc_a_id=doc_a_str,
            doc_b_id=doc_b_str,
            principal=None,
            divergence_index=response.statistics.divergence_index if response.statistics else 0.0,
            conflicts_count=response.statistics.conflicting_clauses_count if response.statistics else 0,
            latency_ms=response.diagnostics.total_latency_ms if response.diagnostics else 0.0,
            db=db,
        )
        return response
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document comparison failed: {str(e)}",
        )
