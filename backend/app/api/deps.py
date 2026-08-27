"""
FastAPI Authentication, Security & RBAC Dependencies.
Provides OAuth2 bearer token extraction, cryptographic JWT resolution, database-authoritative
user validation, role checking, clearance guards, and token invalidation enforcement.
"""
from typing import Callable, List, Optional
import uuid
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.security import (
    AuthSecurityError,
    ExpiredTokenError,
    InvalidSignatureError,
    InvalidTokenError,
    decode_access_token,
)
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.audit import AuditEventType, AuditSeverity, AuthorizationResult
from backend.app.schemas.auth import RBACContext
from backend.app.services.audit_service import audit_service
from backend.app.services.auth_service import auth_service
from backend.app.services.security_observability import security_observability

# OAuth2 scheme for extracting Bearer token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extracts Bearer token, validates cryptographic signature & expiration,
    and resolves the authoritative current user from the database.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    req_path = request.url.path

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AuthSecurityError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: subject is not a valid UUID.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Database-Authoritative resolution
    stmt = select(User).where(User.id == user_uuid)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token does not exist.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        await audit_service.record_event(
            event_type=AuditEventType.AUTH_ACCOUNT_DISABLED,
            action="access_attempt_deactivated_account",
            severity=AuditSeverity.HIGH,
            principal=user,
            resource_type="user",
            resource_id=str(user.id),
            authorization_result=AuthorizationResult.DENIED,
            source_ip=client_ip,
            user_agent=user_agent,
            api_path=req_path,
            status_code=401,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Token version invalidation check
    token_ver = payload.get("token_version", 1)
    if token_ver != getattr(user, "token_version", 1):
        await audit_service.record_event(
            event_type=AuditEventType.AUTH_TOKEN_REVOKED,
            action="access_attempt_revoked_token",
            severity=AuditSeverity.HIGH,
            principal=user,
            resource_type="token",
            resource_id=str(user.id),
            authorization_result=AuthorizationResult.DENIED,
            source_ip=client_ip,
            user_agent=user_agent,
            api_path=req_path,
            status_code=401,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency ensuring active user state."""
    return current_user


async def get_current_rbac_context(
    current_user: User = Depends(get_current_active_user),
) -> RBACContext:
    """Dependency returning authoritative RBACContext."""
    return auth_service.get_user_rbac_context(current_user)


def require_roles(required_roles: List[str]) -> Callable:
    """
    Dependency factory checking if the authenticated user has at least one of the required roles.
    Admins bypass role restrictions.
    """
    async def role_checker(
        request: Request,
        rbac: RBACContext = Depends(get_current_rbac_context),
        db: AsyncSession = Depends(get_db),
    ) -> RBACContext:
        if rbac.is_admin:
            return rbac
        if any(role in rbac.roles for role in required_roles):
            return rbac

        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        req_path = request.url.path

        # Record authorization denial audit event
        await audit_service.record_authorization_denied(
            principal=rbac,
            action="role_access_denied",
            resource_type="endpoint",
            resource_id=req_path,
            reason=f"Requires one of roles: {required_roles}",
            api_path=req_path,
            http_method=request.method,
            status_code=403,
            source_ip=client_ip,
            user_agent=user_agent,
            db=db,
        )
        # Evaluate anomaly threshold for repeated authorization denials
        await security_observability.evaluate_authorization_denial_anomaly(
            user_id=rbac.user_id,
            email=rbac.email,
            db=db,
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Requires one of roles: {required_roles}.",
        )
    return role_checker


def require_clearance(min_level: int) -> Callable:
    """
    Dependency factory enforcing minimum security clearance level (L1-L4).
    """
    async def clearance_checker(
        request: Request,
        rbac: RBACContext = Depends(get_current_rbac_context),
        db: AsyncSession = Depends(get_db),
    ) -> RBACContext:
        if rbac.is_admin or rbac.clearance_level >= min_level:
            return rbac

        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        req_path = request.url.path

        # Record clearance denial audit event
        await audit_service.record_authorization_denied(
            principal=rbac,
            action="clearance_access_denied",
            resource_type="endpoint",
            resource_id=req_path,
            reason=f"Insufficient security clearance (requires L{min_level}, current L{rbac.clearance_level})",
            api_path=req_path,
            http_method=request.method,
            status_code=403,
            source_ip=client_ip,
            user_agent=user_agent,
            db=db,
        )
        await security_observability.evaluate_authorization_denial_anomaly(
            user_id=rbac.user_id,
            email=rbac.email,
            db=db,
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Insufficient security clearance (requires L{min_level}, current L{rbac.clearance_level}).",
        )
    return clearance_checker


require_admin = require_roles(["Admin"])

