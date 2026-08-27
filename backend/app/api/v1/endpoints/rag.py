"""
Grounded RAG Query & Synthesis API Endpoint.
Exposes POST /api/v1/rag/query with telemetry logging and degraded mode fault-tolerance.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.query_log import QueryLog
from backend.app.db.session import get_db
from backend.app.schemas.rag import RAGAnswer, RAGQueryRequest
from backend.app.services.rag_pipeline import RAGPipelineService, rag_pipeline_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=RAGAnswer,
    status_code=status.HTTP_200_OK,
    summary="Execute Grounded RAG Query",
    description=(
        "Executes end-to-end grounded document intelligence: "
        "Parallel Hybrid Retrieval (Dense+BM25) -> ONNX Cross-Encoder Reranking -> "
        "Context Compression -> XML Sandboxed Synthesis -> Deterministic Citation & Grounding Verification."
    ),
)
async def query_rag(
    request: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    pipeline: RAGPipelineService = Depends(lambda: rag_pipeline_service),
) -> RAGAnswer:
    """
    Handles user RAG search query, executes multi-phase synthesis pipeline,
    records observability telemetry into QueryLog, and returns structured RAGAnswer.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty or solely whitespace.",
        )

    try:
        answer: RAGAnswer = await pipeline.query(request)
    except Exception as e:
        logger.error("RAG pipeline execution failure: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute RAG synthesis pipeline: {str(e)}",
        )

    # Asynchronously persist query telemetry into QueryLog ORM model
    try:
        chunk_ids = [str(c.chunk_id) for c in answer.citations]
        query_log_record = QueryLog(
            raw_query=request.query,
            retrieved_chunk_ids=chunk_ids,
            llm_response=answer.answer,
            latency_ms=answer.diagnostics.total_rag_latency_ms,
            prompt_tokens=answer.diagnostics.prompt_tokens,
            completion_tokens=answer.diagnostics.completion_tokens,
        )
        db.add(query_log_record)
        await db.commit()
    except Exception as log_err:
        # Avoid failing user response if telemetry logging encounters DB issue
        logger.warning("Failed to record QueryLog telemetry: %s", log_err)
        await db.rollback()

    # Record Phase 11 privacy-preserving RAG query audit event
    from backend.app.services.audit_service import audit_service
    await audit_service.record_rag_event(
        query=request.query,
        principal=None,
        citations_count=len(answer.citations),
        grounding_status=answer.grounding_status.value if hasattr(answer.grounding_status, "value") else str(answer.grounding_status),
        latency_ms=answer.diagnostics.total_rag_latency_ms if answer.diagnostics else 0.0,
        degraded_mode=answer.diagnostics.degraded_mode if answer.diagnostics else False,
        conflicts_detected=answer.conflicts_detected,
        db=db,
    )

    return answer
