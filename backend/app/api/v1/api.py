from fastapi import APIRouter
from backend.app.api.v1.endpoints import audit, auth, comparison, documents, health, rag

api_router = APIRouter()

# Include health check endpoints under /api/v1
api_router.include_router(health.router, tags=["System Health"])

# Include authentication & user management endpoints under /api/v1/auth
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & RBAC"])

# Include document upload & management endpoints under /api/v1/documents
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

# Include document comparison & diff intelligence endpoints under /api/v1/documents
api_router.include_router(comparison.router, prefix="/documents", tags=["Document Comparison & Diff"])

# Include Grounded RAG synthesis endpoints under /api/v1/rag
api_router.include_router(rag.router, prefix="/rag", tags=["RAG Synthesis & Verification"])

# Include Phase 11 Administrative Audit Logging & Security Observability under /api/v1/audit
api_router.include_router(audit.router, prefix="/audit", tags=["Audit & Security Observability"])
