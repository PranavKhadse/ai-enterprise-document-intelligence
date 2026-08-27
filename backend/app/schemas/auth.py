"""
Phase 10 Authentication, JWT, User Management & RBAC Schemas.
Defines strongly typed Pydantic models for user registration, authentication tokens,
role responses, and authoritative server-side RBAC contexts.
"""
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleResponse(BaseModel):
    """Role DTO representing authorization tier."""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None


class DepartmentResponse(BaseModel):
    """Department DTO representing organizational unit."""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None


class UserRegisterRequest(BaseModel):
    """Request payload for new user registration."""
    model_config = ConfigDict(frozen=True)

    email: str = Field(..., description="User corporate email address")
    password: str = Field(..., min_length=8, description="Plaintext password (minimum 8 characters)")
    department_id: Optional[uuid.UUID] = Field(default=None, description="Optional primary department ID")
    role_names: List[str] = Field(
        default_factory=lambda: ["Employee"],
        description="Requested roles (privileged roles like Admin/Legal cannot be self-assigned)",
    )


class UserLoginRequest(BaseModel):
    """Request payload for user authentication and JWT generation."""
    model_config = ConfigDict(frozen=True)

    email: str = Field(..., description="User corporate email address")
    password: str = Field(..., description="Plaintext password")


class UserResponse(BaseModel):
    """Safe user profile response omitting password hashes and sensitive internal state."""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    email: str
    is_active: bool
    department_id: Optional[uuid.UUID] = None
    department: Optional[DepartmentResponse] = None
    roles: List[str] = Field(default_factory=list, description="Assigned role names")
    clearance_level: int = Field(default=1, ge=1, le=4, description="Effective security clearance level (L1-L4)")


class TokenResponse(BaseModel):
    """Response payload containing JWT bearer token and user metadata."""
    model_config = ConfigDict(frozen=True)

    access_token: str = Field(description="HMAC-SHA256 signed JWT access token")
    token_type: str = Field(default="bearer", description="Token type standard ('bearer')")
    expires_in: int = Field(description="Token validity duration in seconds")
    user: UserResponse = Field(description="Current authenticated user details")


class RBACContext(BaseModel):
    """Authoritative server-resolved security and access control context."""
    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    email: str
    roles: List[str] = Field(default_factory=list)
    department_id: Optional[uuid.UUID] = None
    clearance_level: int = Field(default=1, ge=1, le=4)
    is_admin: bool = Field(default=False)
    token_version: int = Field(default=1)
