from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.v1.api import api_router
from backend.app.core.config import settings
from backend.app.core.request_context import RequestContextMiddleware
from backend.app.schemas.health import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown lifecycle events.
    """
    # Startup logic (e.g., connection pools, cache warming)
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
