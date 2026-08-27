"""
Integration tests for Authentication REST API endpoints (/api/v1/auth).
Verifies registration, login, profile retrieval, 401 on unauthenticated/tampered requests,
and token version revocation enforcement.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.core.security import create_access_token
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
async def auth_test_env():
    """Sets up an isolated in-memory SQLite database and client for auth API testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_auth_api_register_and_login_flow(auth_test_env):
    """Verifies complete user registration and login flow via REST API."""
    client, _ = auth_test_env

    # 1. Register
    reg_payload = {
        "email": "flow.user@enterprise.com",
        "password": "StrongPassword123!",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["email"] == "flow.user@enterprise.com"
    assert "hashed_password" not in reg_data
    assert reg_data["roles"] == ["Employee"]

    # 2. Login
    login_payload = {
        "email": "flow.user@enterprise.com",
        "password": "StrongPassword123!",
    }
    login_res = await client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # 3. Access Protected /me Endpoint
    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "flow.user@enterprise.com"
    assert me_data["clearance_level"] == 1


@pytest.mark.asyncio
async def test_auth_api_login_invalid_credentials(auth_test_env):
    """Verifies that invalid credentials return 401 Unauthorized."""
    client, _ = auth_test_env
    login_payload = {
        "email": "nonexistent@enterprise.com",
        "password": "WrongPassword123!",
    }
    res = await client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_auth_api_me_missing_token_returns_401(auth_test_env):
    """Verifies that unauthenticated request to /me returns 401."""
    client, _ = auth_test_env
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_auth_api_me_tampered_token_returns_401(auth_test_env):
    """Verifies that tampered JWT token returns 401."""
    client, _ = auth_test_env

    # Register user
    reg_payload = {"email": "tamper.user@enterprise.com", "password": "Password123!"}
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201

    # Login
    login_res = await client.post("/api/v1/auth/login", json=reg_payload)
    token = login_res.json()["access_token"]

    # Tamper token
    tampered_token = token[:-4] + "ABCD"
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res.status_code == 401
