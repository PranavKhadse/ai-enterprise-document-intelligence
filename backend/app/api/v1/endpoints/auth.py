"""
Authentication and User Management Endpoints.
Provides REST APIs for user registration, JWT login, and current authenticated profile retrieval.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_active_user
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from backend.app.services.auth_service import auth_service

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
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Registers a new user and returns safe profile data."""
    try:
        user_response = await auth_service.register_user(request, db)
        return user_response
    except ValueError as ve:
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
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticates credentials and returns signed JWT token with user details."""
    user = await auth_service.authenticate_user(request.email, request.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
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
