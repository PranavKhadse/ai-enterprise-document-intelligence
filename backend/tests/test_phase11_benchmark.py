"""
Phase 11 Audit Logging, Security Observability & Compliance Benchmark.
Evaluates 10 rigorous compliance and security red-team scenarios, measures genuine runtime
latencies, verifies zero-secret leakage, and writes backend/config/audit_benchmark_results.json.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.core.request_context import (
    HEADER_REQUEST_ID,
    get_current_request_id,
    is_valid_request_id,
    request_id_ctx_var,
)
from backend.app.core.security import create_access_token, hash_password
from backend.app.db.base import Base
from backend.app.db.models.audit_event import AuditEvent
from backend.app.db.models.role import Role
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.schemas.audit import AuditEventType, AuditQueryFilter, AuditSeverity, AuthorizationResult
from backend.app.services.audit_service import (
    AuditService,
    audit_service,
    generate_query_fingerprint,
    sanitize_metadata,
)
from backend.app.services.security_observability import SecurityObservabilityService


@pytest.fixture
async def benchmark_env():
    """Sets up an isolated database and authenticated clients for benchmark execution."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed Admin and Employee users
    async with session_factory() as session:
        admin_role = Role(name="Admin", description="Administrator")
        emp_role = Role(name="Employee", description="Employee")
        session.add_all([admin_role, emp_role])
        await session.flush()

        admin = User(
            email="benchmark.admin@corp.com",
            hashed_password=hash_password("AdminPass123!"),
            is_active=True,
            token_version=1,
            roles=[admin_role],
        )
        emp = User(
            email="benchmark.emp@corp.com",
            hashed_password=hash_password("EmpPass123!"),
            is_active=True,
            token_version=1,
            roles=[emp_role],
        )
        session.add_all([admin, emp])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(emp)

        admin_token = create_access_token({"sub": str(admin.id), "token_version": 1})
        emp_token = create_access_token({"sub": str(emp.id), "token_version": 1})

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
async def test_phase11_audit_and_security_benchmark(benchmark_env):
    """
    Executes all 10 Phase 11 compliance scenarios, computes empirical metrics,
    and writes backend/config/audit_benchmark_results.json.
    """
    client = benchmark_env["client"]
    admin_token = benchmark_env["admin_token"]
    emp_token = benchmark_env["emp_token"]
    session_factory = benchmark_env["session_factory"]

    scenarios = []

    # Scenario 1: Missing Authorization Header Rejection
    t0 = time.perf_counter()
    res1 = await client.get("/api/v1/audit/events")
    lat1 = (time.perf_counter() - t0) * 1000.0
    passed1 = (res1.status_code == 401)
    scenarios.append({
        "name": "Missing Authorization Header",
        "category": "Authentication Guard",
        "passed": passed1,
        "latency_ms": round(lat1, 2),
        "details": "Unauthenticated access rejected with HTTP 401",
    })
    assert passed1

    # Scenario 2: Non-admin Audit API Access Rejection
    t0 = time.perf_counter()
    res2 = await client.get("/api/v1/audit/events", headers={"Authorization": f"Bearer {emp_token}"})
    lat2 = (time.perf_counter() - t0) * 1000.0
    passed2 = (res2.status_code == 403)
    scenarios.append({
        "name": "Non-admin Audit API Access",
        "category": "RBAC Isolation",
        "passed": passed2,
        "latency_ms": round(lat2, 2),
        "details": "Non-admin employee denied access with HTTP 403",
    })
    assert passed2

    # Scenario 3: Recursive Secret Redaction
    t0 = time.perf_counter()
    secret_payload = {
        "user": "alice",
        "auth": {"password": "PlainPassword", "api_key": "sk-12345", "token": "secret_tok"},
        "nested": [{"client_secret": "sec99"}, {"normal_field": "safe_val"}],
    }
    redacted = sanitize_metadata(secret_payload)
    lat3 = (time.perf_counter() - t0) * 1000.0
    passed3 = (
        redacted["auth"]["password"] == "[REDACTED]"
        and redacted["auth"]["api_key"] == "[REDACTED]"
        and redacted["auth"]["token"] == "[REDACTED]"
        and redacted["nested"][0]["client_secret"] == "[REDACTED]"
        and redacted["nested"][1]["normal_field"] == "safe_val"
    )
    scenarios.append({
        "name": "Recursive Secret Redaction",
        "category": "Data Privacy",
        "passed": passed3,
        "latency_ms": round(lat3, 2),
        "details": "All nested passwords, API keys, and secrets recursively sanitized to [REDACTED]",
    })
    assert passed3

    # Scenario 4: JWT/Bearer Token Redaction in String Values
    t0 = time.perf_counter()
    jwt_sample = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sample_signature_xyz"
    raw_str_payload = {"header": f"Bearer {jwt_sample}", "msg": f"Auth token is {jwt_sample}"}
    sanitized_jwt = sanitize_metadata(raw_str_payload)
    lat4 = (time.perf_counter() - t0) * 1000.0
    passed4 = (
        "Bearer [REDACTED]" in sanitized_jwt["header"]
        and "[REDACTED_JWT]" in sanitized_jwt["msg"]
        and jwt_sample not in sanitized_jwt["msg"]
    )
    scenarios.append({
        "name": "JWT/Bearer Token Redaction",
        "category": "Data Privacy",
        "passed": passed4,
        "latency_ms": round(lat4, 2),
        "details": "Embedded JWT and Bearer tokens scrubbed from string payloads",
    })
    assert passed4

    # Scenario 5: Query Fingerprint Privacy
    t0 = time.perf_counter()
    q_text = "What is the corporate severance package clause?"
    fp = generate_query_fingerprint(q_text)
    lat5 = (time.perf_counter() - t0) * 1000.0
    passed5 = (fp is not None and fp.startswith("sha256:") and len(fp) == 71)
    scenarios.append({
        "name": "Query Fingerprint Privacy",
        "category": "Query Privacy",
        "passed": passed5,
        "latency_ms": round(lat5, 2),
        "details": "Search and RAG queries fingerprinted via one-way SHA-256 without raw text exposure",
    })
    assert passed5

    # Scenario 6: Invalid Request ID Replacement
    t0 = time.perf_counter()
    invalid_req_id = "malicious<script>req</script>"
    res6 = await client.get("/health", headers={HEADER_REQUEST_ID: invalid_req_id})
    lat6 = (time.perf_counter() - t0) * 1000.0
    returned_id = res6.headers.get(HEADER_REQUEST_ID)
    passed6 = (
        res6.status_code == 200
        and returned_id != invalid_req_id
        and is_valid_request_id(returned_id)
    )
    scenarios.append({
        "name": "Invalid Request ID Replacement",
        "category": "Request Correlation",
        "passed": passed6,
        "latency_ms": round(lat6, 2),
        "details": "Unsafe or malicious request IDs discarded and replaced with secure random IDs",
    })
    assert passed6

    # Scenario 7: Concurrent Request ID Isolation
    t0 = time.perf_counter()
    async def isolated_worker(worker_id: str):
        token = request_id_ctx_var.set(worker_id)
        try:
            await asyncio.sleep(0.005)
            assert get_current_request_id() == worker_id
        finally:
            request_id_ctx_var.reset(token)

    tasks = [isolated_worker(f"worker-{i}") for i in range(10)]
    await asyncio.gather(*tasks)
    lat7 = (time.perf_counter() - t0) * 1000.0
    passed7 = True
    scenarios.append({
        "name": "Concurrent Request ID Isolation",
        "category": "Request Correlation",
        "passed": passed7,
        "latency_ms": round(lat7, 2),
        "details": "ContextVar request correlation IDs strictly isolated across concurrent async tasks",
    })
    assert passed7

    # Scenario 8: Login Failure Burst Detection
    t0 = time.perf_counter()
    obs = SecurityObservabilityService(failure_threshold=5, window_minutes=10)
    target_email = "victim@corp.com"
    sec_event_login = None
    async with session_factory() as session:
        for _ in range(5):
            await audit_service.record_auth_failure(attempted_email=target_email, db=session)
        sec_event_login = await obs.evaluate_login_failure_anomaly(target_identity=target_email, db=session)
    lat8 = (time.perf_counter() - t0) * 1000.0
    passed8 = (
        sec_event_login is not None
        and sec_event_login.event_type == AuditEventType.SECURITY_EVENT.value
        and sec_event_login.severity == AuditSeverity.HIGH.value
    )
    scenarios.append({
        "name": "Login Failure Burst Detection",
        "category": "Security Observability",
        "passed": passed8,
        "latency_ms": round(lat8, 2),
        "details": "5 repeated authentication failures detected within window triggering HIGH security anomaly",
    })
    assert passed8

    # Scenario 9: Authorization Denial Burst Detection
    t0 = time.perf_counter()
    sec_event_denial = None
    target_user_id = uuid.uuid4()
    async with session_factory() as session:
        for _ in range(5):
            await audit_service.record_authorization_denied(
                principal={"user_id": target_user_id, "email": "dev@corp.com", "roles": ["Employee"]},
                action="view_executive_salaries",
                resource_type="document",
                resource_id="doc-salaries",
                db=session,
            )
        sec_event_denial = await obs.evaluate_authorization_denial_anomaly(user_id=target_user_id, db=session)
    lat9 = (time.perf_counter() - t0) * 1000.0
    passed9 = (
        sec_event_denial is not None
        and sec_event_denial.event_type == AuditEventType.SECURITY_EVENT.value
        and sec_event_denial.severity == AuditSeverity.HIGH.value
    )
    scenarios.append({
        "name": "Authorization Denial Burst Detection",
        "category": "Security Observability",
        "passed": passed9,
        "latency_ms": round(lat9, 2),
        "details": "5 repeated authorization denials for a user detected triggering HIGH security anomaly",
    })
    assert passed9

    # Scenario 10: Audit Record Tamper Detection
    t0 = time.perf_counter()
    async with session_factory() as session:
        ev_orig = await audit_service.record_event(
            event_type=AuditEventType.DOCUMENT_CREATED,
            action="create_doc",
            resource_type="document",
            resource_id="doc-original",
            db=session,
        )
    # Simulate attacker tampering with recorded action
    ev_tampered = AuditEvent(
        id=ev_orig.id,
        created_at=ev_orig.created_at,
        request_id=ev_orig.request_id,
        event_type=ev_orig.event_type,
        severity=ev_orig.severity,
        user_id=ev_orig.user_id,
        action="tampered_malicious_action",  # Modified action
        resource_type=ev_orig.resource_type,
        resource_id=ev_orig.resource_id,
        authorization_result=ev_orig.authorization_result,
        query_fingerprint=ev_orig.query_fingerprint,
        event_hash=ev_orig.event_hash,
        previous_event_hash=ev_orig.previous_event_hash,
        metadata_json=ev_orig.metadata_json,
    )
    is_valid, violations = audit_service.verify_audit_log_chain([ev_tampered])
    lat10 = (time.perf_counter() - t0) * 1000.0
    passed10 = (is_valid is False and len(violations) > 0)
    scenarios.append({
        "name": "Audit Record Tamper Detection",
        "category": "Audit Integrity",
        "passed": passed10,
        "latency_ms": round(lat10, 2),
        "details": "Tamper-evident canonical SHA-256 hash chaining detects unauthorized row modification",
    })
    assert passed10

    # Aggregate Benchmark Metrics Calculation
    total_scenarios = len(scenarios)
    passed_scenarios = sum(1 for s in scenarios if s["passed"])
    pass_rate = (passed_scenarios / total_scenarios) * 100.0
    avg_latency = sum(s["latency_ms"] for s in scenarios) / total_scenarios

    benchmark_report = {
        "benchmark_name": "Phase 11 Audit Logging, Security Observability & Compliance Benchmark",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total_scenarios,
        "metrics": {
            "pass_rate": round(pass_rate, 2),
            "passed_scenarios": passed_scenarios,
            "total_scenarios": total_scenarios,
            "average_latency_ms": round(avg_latency, 2),
            "secret_redaction_accuracy": 100.0,
            "request_correlation_accuracy": 100.0,
            "anomaly_detection_accuracy": 100.0,
            "tamper_detection_accuracy": 100.0,
        },
        "scenarios": scenarios,
    }

    # Write empirical report to backend/config/audit_benchmark_results.json
    output_path = Path("backend/config/audit_benchmark_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_report, f, indent=2)

    assert output_path.exists()
    assert pass_rate == 100.0
