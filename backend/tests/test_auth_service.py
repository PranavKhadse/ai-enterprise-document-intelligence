"""
Unit tests for AuthService (backend/app/services/auth_service.py).
Verifies user registration, privilege escalation defense, role resolution,
clearance level computation, authentication verification, and token generation.
"""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models.department import Department
from backend.app.db.models.role import Role
from backend.app.db.models.user import User
from backend.app.schemas.auth import UserRegisterRequest
from backend.app.services.auth_service import AuthService, auth_service


@pytest.fixture
async def db_session():
    """Provides an isolated in-memory SQLite database session for unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_register_user_default_employee(db_session: AsyncSession):
    """Verifies that public registration assigns Employee role and L1 clearance."""
    req = UserRegisterRequest(
        email="john.doe@enterprise.com",
        password="SecurePassword123!",
    )
    user_resp = await auth_service.register_user(req, db_session)

    assert user_resp.email == "john.doe@enterprise.com"
    assert user_resp.roles == ["Employee"]
    assert user_resp.clearance_level == 1
    assert user_resp.is_active is True


@pytest.mark.asyncio
async def test_register_user_privilege_escalation_blocked(db_session: AsyncSession):
    """Verifies that attempts to self-assign Admin or Legal are blocked and downgraded to Employee."""
    req = UserRegisterRequest(
        email="attacker@enterprise.com",
        password="AttackerPassword123!",
        role_names=["Admin", "Legal"],
    )
    user_resp = await auth_service.register_user(req, db_session, is_admin_creation=False)

    # Admin and Legal must be stripped
    assert "Admin" not in user_resp.roles
    assert "Legal" not in user_resp.roles
    assert user_resp.roles == ["Employee"]
    assert user_resp.clearance_level == 1


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(db_session: AsyncSession):
    """Verifies that duplicate registration with the same email raises ValueError."""
    req = UserRegisterRequest(
        email="dup.user@enterprise.com",
        password="Password123!",
    )
    await auth_service.register_user(req, db_session)

    with pytest.raises(ValueError, match="already exists"):
        await auth_service.register_user(req, db_session)


@pytest.mark.asyncio
async def test_authenticate_user_success_and_failure(db_session: AsyncSession):
    """Verifies password authentication returns user on match and None on mismatch."""
    email = "auth.test@enterprise.com"
    password = "CorrectPassword123!"
    req = UserRegisterRequest(email=email, password=password)
    await auth_service.register_user(req, db_session)

    # Valid
    authenticated = await auth_service.authenticate_user(email, password, db_session)
    assert authenticated is not None
    assert authenticated.email == email

    # Wrong password
    wrong = await auth_service.authenticate_user(email, "WrongPassword", db_session)
    assert wrong is None

    # Unknown email
    unknown = await auth_service.authenticate_user("nonexistent@enterprise.com", password, db_session)
    assert unknown is None


@pytest.mark.asyncio
async def test_authenticate_inactive_user(db_session: AsyncSession):
    """Verifies that deactivated accounts cannot authenticate."""
    email = "inactive@enterprise.com"
    password = "Password123!"
    req = UserRegisterRequest(email=email, password=password)
    user_resp = await auth_service.register_user(req, db_session)

    # Deactivate user
    user = await db_session.get(User, user_resp.id)
    user.is_active = False
    await db_session.commit()

    authenticated = await auth_service.authenticate_user(email, password, db_session)
    assert authenticated is None


def test_clearance_calculation_hierarchy():
    """Verifies clearance hierarchy mapping (Admin=4, Legal=3, HR_Manager=2, Employee=1)."""
    assert auth_service.calculate_clearance_level(["Employee"]) == 1
    assert auth_service.calculate_clearance_level(["HR_Manager"]) == 2
    assert auth_service.calculate_clearance_level(["Legal"]) == 3
    assert auth_service.calculate_clearance_level(["Admin"]) == 4
    assert auth_service.calculate_clearance_level(["Employee", "Legal"]) == 3
    assert auth_service.calculate_clearance_level([]) == 1


@pytest.mark.asyncio
async def test_create_token_for_user(db_session: AsyncSession):
    """Verifies token generation contains valid claims and token version."""
    email = "token.user@enterprise.com"
    req = UserRegisterRequest(email=email, password="Password123!")
    user_resp = await auth_service.register_user(req, db_session)
    user = await db_session.get(User, user_resp.id)

    token_resp = auth_service.create_token_for_user(user)
    assert token_resp.token_type == "bearer"
    assert token_resp.access_token is not None
    assert token_resp.expires_in > 0
    assert token_resp.user.email == email
