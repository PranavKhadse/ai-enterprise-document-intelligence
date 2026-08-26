from fastapi import APIRouter, status
from backend.app.core.config import settings
from backend.app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns the operational status, environment, version, and current UTC timestamp."
)
async def check_health() -> HealthResponse:
    """
    Health check endpoint for container orchestrators, load balancers, and monitoring tools.
    """
    return HealthResponse(
        status="healthy",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )
