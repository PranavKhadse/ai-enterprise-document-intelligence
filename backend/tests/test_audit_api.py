"""
Integration tests for Admin Audit REST API endpoints (/api/v1/audit).
Verifies strict require_admin RBAC protection, 401/403 rejections, filtering, pagination,
individual event retrieval, and aggregated statistics calculation.
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.core.security import create_access_token, hash_password
from backend.app.db.base import Base
from backend.app.db.models.role import Role
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.schemas.audit import AuditEventType, AuditSeverity, AuthorizationResult
from backend.app.services.audit_service import audit_service


@pytest.fixture
async def audit_api_env():
    """Sets up an isolated database, test users (admin and employee), and HTTP test client."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed roles and users
    async with session_factory() as session:
        admin_role = Role(name="Admin", description="System Administrator")
        emp_role = Role(name="Employee", description="Standard Employee")
        session.add_all([admin_role, emp_role])
        await session.flush()

        admin_user = User(
            email="admin@enterprise.com",
            hashed_password=hash_password("AdminPass123!"),
            is_active=True,
            token_version=1,
            roles=[admin_role],
        )
        emp_user = User(
            email="employee@enterprise.com",
            hashed_password=hash_password("EmpPass123!"),
            is_active=True,
            token_version=1,
            roles=[emp_role],
        )
        session.add_all([admin_user, emp_user])
        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(emp_user)

        admin_token = create_access_token({"sub": str(admin_user.id), "token_version": 1})
        emp_token = create_access_token({"sub": str(emp_user.id), "token_version": 1})

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
        yield {
            "client": client,
            "admin_token": admin_token,
            "emp_token": emp_token,
            "session_factory": session_factory,
        }

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_api_unauthenticated_returns_401(audit_api_env):
    """Verifies that unauthenticated requests to /api/v1/audit/events return 401."""
    client = audit_api_env["client"]
    res = await client.get("/api/v1/audit/events")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_audit_api_non_admin_returns_403(audit_api_env):
    """Verifies that standard employees (non-admins) receive 403 Forbidden on audit endpoints."""
    client = audit_api_env["client"]
    emp_headers = {"Authorization": f"Bearer {audit_api_env['emp_token']}"}

    res_events = await client.get("/api/v1/audit/events", headers=emp_headers)
    assert res_events.status_code == 403

    res_stats = await client.get("/api/v1/audit/statistics", headers=emp_headers)
    assert res_stats.status_code == 403


@pytest.mark.asyncio
async def test_audit_api_admin_query_and_pagination(audit_api_env):
    """Verifies that an Admin can query audit events, filter by severity, and paginate."""
    client = audit_api_env["client"]
    admin_headers = {"Authorization": f"Bearer {audit_api_env['admin_token']}"}
    session_factory = audit_api_env["session_factory"]

    # Seed 5 audit records
    async with session_factory() as session:
        for i in range(5):
            await audit_service.record_event(
                event_type=AuditEventType.DOCUMENT_READ if i % 2 == 0 else AuditEventType.AUTH_LOGIN_FAILURE,
                action=f"action_{i}",
                severity=AuditSeverity.INFO if i % 2 == 0 else AuditSeverity.HIGH,
                resource_type="document" if i % 2 == 0 else "user",
                resource_id=f"doc_{i}",
                db=session,
            )

    # Query with limit 3
    res = await client.get("/api/v1/audit/events?limit=3&offset=0", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["limit"] == 3
    assert len(data["items"]) == 3
    assert data["total"] >= 5

    # Filter by severity=high
    res_high = await client.get("/api/v1/audit/events?severity=high", headers=admin_headers)
    assert res_high.status_code == 200
    high_data = res_high.json()
    for item in high_data["items"]:
        assert item["severity"] == "high"


@pytest.mark.asyncio
async def test_audit_api_get_single_event_and_statistics(audit_api_env):
    """Verifies single event lookup by UUID and aggregate statistics computation."""
    client = audit_api_env["client"]
    admin_headers = {"Authorization": f"Bearer {audit_api_env['admin_token']}"}
    session_factory = audit_api_env["session_factory"]

    # Record a test event
    created_event = None
    async with session_factory() as session:
        created_event = await audit_service.record_event(
            event_type=AuditEventType.RAG_QUERY,
            action="rag_search",
            severity=AuditSeverity.INFO,
            resource_type="rag",
            raw_query="Find compliance docs",
            db=session,
        )

    assert created_event is not None

    # Fetch event by UUID
    res_single = await client.get(f"/api/v1/audit/events/{created_event.id}", headers=admin_headers)
    assert res_single.status_code == 200
    item = res_single.json()
    assert item["id"] == str(created_event.id)
    assert item["event_type"] == "rag_query"

    # Fetch non-existent UUID
    fake_id = uuid.uuid4()
    res_404 = await client.get(f"/api/v1/audit/events/{fake_id}", headers=admin_headers)
    assert res_404.status_code == 404

    # Fetch statistics
    res_stats = await client.get("/api/v1/audit/statistics", headers=admin_headers)
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_events"] >= 1
    assert "events_by_type" in stats
    assert "events_by_severity" in stats
