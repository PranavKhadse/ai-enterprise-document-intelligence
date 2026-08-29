import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from backend.app.api.v1.api import api_router
from backend.app.core.config import settings
from backend.app.core.request_context import RequestContextMiddleware
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.db.session import AsyncSessionLocal
from backend.app.schemas.health import HealthResponse
from backend.app.services.bm25 import bm25_service

logger = logging.getLogger(__name__)


async def _warmup_bm25_index() -> None:
    """
    Safely warms up the BM25 sparse lexical index during application startup.
    1. Attempts to load from disk (data/bm25_index.pkl).
    2. If index is empty, synchronizes chunks from PostgreSQL so existing documents are immediately searchable.
    """
    try:
        try:
            loaded = bm25_service.load_from_disk()
            if loaded:
                logger.info("Loaded BM25 index from disk (%d documents indexed).", bm25_service.corpus_size)
        except Exception as load_err:
            logger.warning("Could not load BM25 index from disk: %s. Rebuilding from database...", load_err)

        if bm25_service.corpus_size == 0:
            logger.info("BM25 index is empty. Synchronizing chunks from PostgreSQL...")
            async with AsyncSessionLocal() as session:
                doc_stmt = select(Document)
                doc_res = await session.execute(doc_stmt)
                documents = doc_res.scalars().all()

                total_chunks_indexed = 0
                for doc in documents:
                    chunk_stmt = (
                        select(DocumentChunk)
                        .where(DocumentChunk.document_id == doc.id)
                        .order_by(DocumentChunk.chunk_index.asc())
                    )
                    chunk_res = await session.execute(chunk_stmt)
                    chunks = chunk_res.scalars().all()
                    if chunks:
                        count = bm25_service.index_chunks(chunks=chunks, document=doc)
                        total_chunks_indexed += count

                logger.info(
                    "BM25 index warmup completed: indexed %d chunks across %d documents.",
                    total_chunks_indexed,
                    len(documents),
                )
    except Exception as e:
        logger.error("Failed to warm up BM25 index during startup: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown lifecycle events.
    """
    # Startup logic: Warm up BM25 sparse index from disk / PostgreSQL
    await _warmup_bm25_index()
    yield
    # Shutdown logic (e.g., closing connection pools)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise-grade document intelligence, hybrid search, and grounded RAG platform.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure Request Correlation Middleware (X-Request-ID)
app.add_middleware(RequestContextMiddleware)

# Configure CORS Middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Root health check endpoint (convenience for top-level load balancers)
@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["System Health"],
    summary="Root Health Check",
)
async def root_health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )


# Root information endpoint
@app.get("/", tags=["System Information"])
async def root_info():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": "/health",
        "api_v1": settings.API_V1_STR,
    }


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
