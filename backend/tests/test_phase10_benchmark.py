"""
Phase 10 Red-Team Security & RBAC Benchmark.
Evaluates 10 adversarial attack scenarios and security policy vectors:
1. Missing Authorization Header
2. Expired JWT Access Token
3. Tampered Cryptographic Signature
4. Tampered JWT Claims Payload
5. alg=none Algorithm Confusion Attack
6. Role-Tampered Client Claims vs Database Authoritative State
7. Registration Privilege Escalation Defense (Self-Assigned Admin/Legal)
8. Multi-Tenant Department Cross-Access Pre-Retrieval Leakage
9. Security Clearance Cross-Access Pre-Retrieval Leakage
10. Server-Side Token Invalidation & Version Revocation

Produces empirical benchmark artifact: backend/config/rbac_benchmark_results.json
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.core.config import settings
from backend.app.core.security import (
    ExpiredTokenError,
    InvalidSignatureError,
    create_access_token,
    decode_access_token,
    hash_password,
)
from backend.app.db.base import Base
from backend.app.db.models.department import Department
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.db.models.role import Role
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.schemas.auth import UserRegisterRequest
from backend.app.services.auth_service import auth_service
from backend.app.services.bm25 import BM25IndexService


@pytest.mark.asyncio
async def test_phase10_rbac_red_team_benchmark():
    """
    Executes the 10 Phase 10 Red-Team security benchmarks and generates rbac_benchmark_results.json.
    """
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

    scenarios = []

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-seed test user
        reg_payload = {"email": "benchmark.user@enterprise.com", "password": "SecurePassword123!"}
        reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201
        user_data = reg_res.json()
        user_uuid = uuid.UUID(user_data["id"])

        login_res = await client.post("/api/v1/auth/login", json=reg_payload)
        assert login_res.status_code == 200
        valid_token = login_res.json()["access_token"]

        # -------------------------------------------------------------
        # Scenario 1: Missing Authorization Header
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        res = await client.get("/api/v1/auth/me")
        lat1 = (time.perf_counter() - t0) * 1000.0
        passed1 = res.status_code == 401
        scenarios.append({
            "id": 1,
            "name": "missing_authorization_header",
            "description": "Unauthenticated request without Authorization header returns 401",
            "defense_mechanism": "FastAPI OAuth2PasswordBearer dependency guard",
            "passed": passed1,
            "latency_ms": round(lat1, 2),
        })

        # -------------------------------------------------------------
        # Scenario 2: Expired JWT Token
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        expired_token = create_access_token(
            {"sub": str(user_uuid), "token_version": 1},
            expires_delta=timedelta(seconds=-60),
        )
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        lat2 = (time.perf_counter() - t0) * 1000.0
        passed2 = res.status_code == 401
        scenarios.append({
            "id": 2,
            "name": "expired_jwt_token",
            "description": "Cryptographically expired token is rejected with 401",
            "defense_mechanism": "Cryptographic 'exp' timestamp verification",
            "passed": passed2,
            "latency_ms": round(lat2, 2),
        })

        # -------------------------------------------------------------
        # Scenario 3: Tampered Cryptographic Signature
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        parts = valid_token.split(".")
        tampered_sig_token = f"{parts[0]}.{parts[1]}.{parts[2][:-4]}XXXX"
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_sig_token}"})
        lat3 = (time.perf_counter() - t0) * 1000.0
        passed3 = res.status_code == 401
        scenarios.append({
            "id": 3,
            "name": "tampered_signature",
            "description": "Token with modified signature bytes is rejected with 401",
            "defense_mechanism": "HMAC-SHA256 constant-time signature verification",
            "passed": passed3,
            "latency_ms": round(lat3, 2),
        })

        # -------------------------------------------------------------
        # Scenario 4: Tampered JWT Claims Payload
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        # Modifying payload segment while keeping original signature
        tampered_payload_token = f"{parts[0]}.eyJzdWIiOiJhZG1pbiIsInJvbGVzIjpbIkFkbWluIl19.{parts[2]}"
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_payload_token}"})
        lat4 = (time.perf_counter() - t0) * 1000.0
        passed4 = res.status_code == 401
        scenarios.append({
            "id": 4,
            "name": "tampered_payload_claims",
            "description": "Token with tampered payload claims triggers signature mismatch 401",
            "defense_mechanism": "Cryptographic payload-signature binding integrity check",
            "passed": passed4,
            "latency_ms": round(lat4, 2),
        })

        # -------------------------------------------------------------
        # Scenario 5: alg=none Algorithm Confusion Attack
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        none_token = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJhZG1pbiJ9."
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_token}"})
        lat5 = (time.perf_counter() - t0) * 1000.0
        passed5 = res.status_code == 401
        scenarios.append({
            "id": 5,
            "name": "alg_none_confusion_attack",
            "description": "alg=none unsigned token attack is strictly rejected with 401",
            "defense_mechanism": "Explicit algorithm validation rejecting 'none' and non-HS256 algorithms",
            "passed": passed5,
            "latency_ms": round(lat5, 2),
        })

        # -------------------------------------------------------------
        # Scenario 6: Role-Tampered Client Claims vs Database Authoritative State
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        # Attacker signs token with valid secret but puts roles=['Admin'] in token, while DB has Employee
        tampered_role_token = create_access_token({
            "sub": str(user_uuid),
            "roles": ["Admin"],
            "clearance": 4,
            "token_version": 1,
        })
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_role_token}"})
        lat6 = (time.perf_counter() - t0) * 1000.0
        # Authoritative endpoint returns DB state (roles=['Employee'], clearance=1), NOT claims in token!
        resp_json = res.json()
        passed6 = res.status_code == 200 and resp_json["roles"] == ["Employee"] and resp_json["clearance_level"] == 1
        scenarios.append({
            "id": 6,
            "name": "role_tampered_authority_inversion",
            "description": "Token claims claiming Admin are superseded by authoritative database state",
            "defense_mechanism": "Database-Authoritative RBAC resolution over client JWT claims",
            "passed": passed6,
            "latency_ms": round(lat6, 2),
        })

        # -------------------------------------------------------------
        # Scenario 7: Registration Privilege Escalation Defense
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        priv_req = {
            "email": "priv.escalation@enterprise.com",
            "password": "Password123!",
            "role_names": ["Admin", "Legal", "HR_Manager"],
        }
        res_esc = await client.post("/api/v1/auth/register", json=priv_req)
        lat7 = (time.perf_counter() - t0) * 1000.0
        esc_data = res_esc.json()
        passed7 = (
            res_esc.status_code == 201
            and esc_data["roles"] == ["Employee"]
            and esc_data["clearance_level"] == 1
        )
        scenarios.append({
            "id": 7,
            "name": "registration_privilege_escalation",
            "description": "Public registration self-assigning Admin/Legal is stripped to Employee (L1)",
            "defense_mechanism": "Privileged role filtering in user registration service",
            "passed": passed7,
            "latency_ms": round(lat7, 2),
        })

        # -------------------------------------------------------------
        # Scenario 8: Multi-Tenant Department Cross-Access Pre-Retrieval Leakage
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        bm25_test = BM25IndexService()
        bm25_test.clear()
        dept_hr = uuid.uuid4()
        dept_eng = uuid.uuid4()

        doc_hr = Document(id=uuid.uuid4(), title="HR Confidential Payroll", department_id=dept_hr)
        chunk_hr = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_hr.id,
            chunk_index=0,
            content="Confidential executive payroll allocations for Q4 fiscal cycle.",
            metadata_json={"department_id": str(dept_hr), "clearance_level": 3},
        )
        doc_eng = Document(id=uuid.uuid4(), title="Engineering Platform", department_id=dept_eng)
        chunk_eng = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_eng.id,
            chunk_index=0,
            content="Platform performance and quarterly release schedule guidelines.",
            metadata_json={"department_id": str(dept_eng), "clearance_level": 1},
        )
        bm25_test.index_document_chunks(doc_hr, [chunk_hr], auto_persist=False)
        bm25_test.index_document_chunks(doc_eng, [chunk_eng], auto_persist=False)

        # Engineering user searches for 'payroll allocations quarterly'
        search_results = bm25_test.search(
            query="payroll allocations quarterly",
            limit=5,
            allowed_department_ids=[dept_eng],
        )
        lat8 = (time.perf_counter() - t0) * 1000.0
        # Must return 0 HR chunks, even though HR chunk matches 'payroll allocations'
        leaked_hr = any(r.document_id == doc_hr.id for r in search_results)
        passed8 = not leaked_hr
        scenarios.append({
            "id": 8,
            "name": "department_cross_access_pre_retrieval",
            "description": "Department pre-filtering guarantees 0 unauthorized department chunks retrieved",
            "defense_mechanism": "Pre-retrieval inverted index metadata boolean constraint evaluation",
            "passed": passed8,
            "latency_ms": round(lat8, 2),
        })

        # -------------------------------------------------------------
        # Scenario 9: Security Clearance Cross-Access Pre-Retrieval Leakage
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        # L1 employee searches for 'executive payroll'
        clearance_results = bm25_test.search(
            query="executive payroll allocations",
            limit=5,
            max_clearance_level=1,
        )
        lat9 = (time.perf_counter() - t0) * 1000.0
        leaked_clearance = any(r.document_id == doc_hr.id for r in clearance_results)
        passed9 = not leaked_clearance
        scenarios.append({
            "id": 9,
            "name": "clearance_cross_access_pre_retrieval",
            "description": "Clearance pre-filtering blocks high-clearance chunks (L3) for L1 queries",
            "defense_mechanism": "Pre-retrieval clearance level ceiling enforcement",
            "passed": passed9,
            "latency_ms": round(lat9, 2),
        })

        # -------------------------------------------------------------
        # Scenario 10: Server-Side Token Invalidation & Version Revocation
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        # Invalidate user token by incrementing token_version in DB
        async with session_factory() as s:
            u = await s.get(User, user_uuid)
            u.token_version = 2
            await s.commit()

        # Present old token with token_version=1
        res_revoked = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
        lat10 = (time.perf_counter() - t0) * 1000.0
        passed10 = res_revoked.status_code == 401
        scenarios.append({
            "id": 10,
            "name": "token_version_revocation",
            "description": "Token with stale token_version is immediately rejected upon server-side increment",
            "defense_mechanism": "Stateful token_version claim validation against database user record",
            "passed": passed10,
            "latency_ms": round(lat10, 2),
        })

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()

    total_scenarios = len(scenarios)
    passed_scenarios = sum(1 for s in scenarios if s["passed"])
    failed_scenarios = total_scenarios - passed_scenarios
    pass_rate = passed_scenarios / total_scenarios if total_scenarios > 0 else 0.0

    report = {
        "benchmark_name": "Phase 10 RBAC & Security Red-Team Benchmark",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "failed_scenarios": failed_scenarios,
        "pass_rate": pass_rate,
        "scenarios": scenarios,
    }

    # Persist benchmark results artifact
    artifact_path = Path("backend/config/rbac_benchmark_results.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    assert total_scenarios == 10
    assert passed_scenarios == 10
    assert failed_scenarios == 0
    assert pass_rate == 1.0
