"""
Authentication, User Management & RBAC Resolution Service.
Handles secure user registration, password verification, database-authoritative role mapping,
and token issuance with privilege escalation defense.
"""
from typing import Dict, List, Optional, Set
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.db.models.department import Department
from backend.app.db.models.role import Role
from backend.app.db.models.user import User
from backend.app.schemas.auth import (
    DepartmentResponse,
    RBACContext,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

# Deterministic clearance hierarchy mapping
ROLE_CLEARANCE_MAP: Dict[str, int] = {
    "Employee": 1,
    "HR_Manager": 2,
    "Legal": 3,
    "Admin": 4,
}

# Roles that cannot be self-assigned during standard public registration
PRIVILEGED_ROLES: Set[str] = {"Admin", "Legal", "HR_Manager"}


class AuthService:
    """
    Core authentication and authorization service with database-authoritative RBAC resolution.
    """

    @staticmethod
    def calculate_clearance_level(roles: List[str]) -> int:
        """Computes effective clearance level as the maximum clearance among assigned roles."""
        if not roles:
            return 1
        clearance = max((ROLE_CLEARANCE_MAP.get(r, 1) for r in roles), default=1)
        return min(max(clearance, 1), 4)

    def get_user_rbac_context(self, user: User) -> RBACContext:
        """
        Builds authoritative RBACContext from current database state.
        """
        role_names = [r.name for r in (user.roles or [])]
        if not role_names:
            role_names = ["Employee"]

        clearance = self.calculate_clearance_level(role_names)
        is_admin = "Admin" in role_names or clearance == 4

        return RBACContext(
            user_id=user.id,
            email=user.email,
            roles=role_names,
            department_id=user.department_id,
            clearance_level=clearance,
            is_admin=is_admin,
            token_version=getattr(user, "token_version", 1),
        )

    def build_user_response(self, user: User) -> UserResponse:
        """Constructs safe UserResponse DTO."""
        role_names = [r.name for r in (user.roles or [])]
        clearance = self.calculate_clearance_level(role_names)

        dept_resp = None
        if user.department:
            dept_resp = DepartmentResponse(
                id=user.department.id,
                name=user.department.name,
                description=user.department.description,
            )

        return UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            department_id=user.department_id,
            department=dept_resp,
            roles=role_names,
            clearance_level=clearance,
        )

    async def register_user(
        self,
        request: UserRegisterRequest,
        db: AsyncSession,
        is_admin_creation: bool = False,
    ) -> UserResponse:
        """
        Registers a new user account with privilege escalation defense.
        """
        clean_email = request.email.lower().strip()

        # Check existing user
        stmt = select(User).where(User.email == clean_email)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ValueError(f"User with email '{clean_email}' already exists.")

        # Defense against privilege escalation: standard registration can only assign Employee role
        assigned_role_names = []
        if is_admin_creation:
            assigned_role_names = request.role_names or ["Employee"]
        else:
            # Filter out any privileged roles requested by client
            assigned_role_names = [r for r in request.role_names if r not in PRIVILEGED_ROLES]
            if not assigned_role_names:
                assigned_role_names = ["Employee"]

        # Resolve or create roles in DB
        roles: List[Role] = []
        for rname in assigned_role_names:
            rstmt = select(Role).where(Role.name == rname)
            r_res = await db.execute(rstmt)
            role_obj = r_res.scalar_one_or_none()
            if not role_obj:
                role_obj = Role(name=rname, description=f"Default {rname} role")
                db.add(role_obj)
                await db.flush()
            roles.append(role_obj)

        # Hash password and create User record
        pwd_hash = hash_password(request.password)
        new_user = User(
            email=clean_email,
            hashed_password=pwd_hash,
            department_id=request.department_id,
            is_active=True,
            token_version=1,
            roles=roles,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        return self.build_user_response(new_user)

    async def authenticate_user(
        self,
        email: str,
        password: str,
        db: AsyncSession,
    ) -> Optional[User]:
        """
        Authenticates email/password against database hash. Returns None if invalid or inactive.
        """
        if not email or not password:
            return None

        clean_email = email.lower().strip()
        stmt = select(User).where(User.email == clean_email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user or not user.is_active:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    def create_token_for_user(self, user: User) -> TokenResponse:
        """
        Generates JWT access token containing current user claims and returns TokenResponse.
        """
        rbac_ctx = self.get_user_rbac_context(user)
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "roles": rbac_ctx.roles,
            "dept": str(user.department_id) if user.department_id else None,
            "clearance": rbac_ctx.clearance_level,
            "token_version": rbac_ctx.token_version,
        }

        token = create_access_token(token_data)
        user_resp = self.build_user_response(user)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_resp,
        )


# Global singleton
auth_service = AuthService()
