from fastapi import APIRouter
from backend.app.api.v1.endpoints import documents, health

api_router = APIRouter()

# Include health check endpoints under /api/v1
api_router.include_router(health.router, tags=["System Health"])

# Include document upload & management endpoints under /api/v1/documents
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
