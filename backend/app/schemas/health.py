from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Schema representing system health status.
    """
    status: str = Field(default="healthy", description="Current service operational status")
    project_name: str = Field(..., description="Name of the service")
    version: str = Field(..., description="Deployed semantic application version")
    environment: str = Field(..., description="Current running environment")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health check"
    )
