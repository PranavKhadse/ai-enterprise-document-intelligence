"""
Authentication and User Management Endpoints.
Provides REST APIs for user registration, JWT login, and current authenticated profile retrieval.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_active_user
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.audit import AuditEventType, AuditSeverity, AuthorizationResult
from backend.app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from backend.app.services.audit_service import audit_service
from backend.app.services.auth_service import auth_service
from backend.app.services.security_observability import security_observability

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
    description="Registers a new corporate user. Privilege escalation is prevented by restricting self-assignment to Employee role.",
)
async def register(
    request: UserRegisterRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Registers a new user and returns safe profile data."""
    try:
        user_response = await auth_service.register_user(request, db)
        await audit_service.record_event(
            event_type=AuditEventType.AUTH_REGISTER,
            action="user_registration",
            severity=AuditSeverity.INFO,
            principal={"user_id": user_response.id, "email": user_response.email, "roles": user_response.roles, "clearance_level": user_response.clearance_level},
            resource_type="user",
            resource_id=str(user_response.id),
            authorization_result=AuthorizationResult.ALLOWED,
            source_ip=req.client.host if req.client else None,
            user_agent=req.headers.get("user-agent"),
            http_method="POST",
            api_path="/api/v1/auth/register",
            status_code=201,
            metadata={"email": user_response.email, "roles": user_response.roles},
            db=db,
        )
        return user_response
    except ValueError as ve:
        await audit_service.record_event(
            event_type=AuditEventType.AUTH_REGISTER,
            action="user_registration_rejected",
            severity=AuditSeverity.WARNING,
            principal=None,
            resource_type="user",
            resource_id=request.email.strip().lower() if request.email else "unknown",
            authorization_result=AuthorizationResult.DENIED,
            source_ip=req.client.host if req.client else None,
            user_agent=req.headers.get("user-agent"),
            http_method="POST",
            api_path="/api/v1/auth/register",
            status_code=400,
            metadata={"attempted_email": request.email, "error": str(ve)},
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive JWT token",
    description="Validates email and password, issuing an HMAC-SHA256 signed access token.",
)
async def login(
    request: UserLoginRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticates credentials and returns signed JWT token with user details."""
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")

    user = await auth_service.authenticate_user(request.email, request.password, db)
    if not user:
        await audit_service.record_auth_failure(
            attempted_email=request.email,
            reason="Invalid credentials",
            source_ip=client_ip,
            user_agent=user_agent,
            db=db,
        )
        # Check anomaly threshold for repeated login failures
        await security_observability.evaluate_login_failure_anomaly(
            target_identity=request.email,
            source_ip=client_ip,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await audit_service.record_auth_success(
        user=user,
        source_ip=client_ip,
        user_agent=user_agent,
        db=db,
    )
    return auth_service.create_token_for_user(user)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the authenticated user's current database-backed roles and security clearance level.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Retrieves current authenticated user's profile."""
    return auth_service.build_user_response(current_user)
