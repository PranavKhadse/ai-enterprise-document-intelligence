"""
Unit tests for Request Correlation and ContextVar Isolation.
Verifies X-Request-ID generation, safe validation, response header injection,
and strict async task isolation.
"""
import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.core.request_context import (
    HEADER_REQUEST_ID,
    generate_request_id,
    get_current_request_id,
    is_valid_request_id,
    request_id_ctx_var,
)
from backend.app.main import app


def test_is_valid_request_id():
    """Verifies format validation constraints for correlation request IDs."""
    assert is_valid_request_id("req-123-abc_XYZ") is True
    assert is_valid_request_id("a" * 64) is True
    assert is_valid_request_id("a" * 65) is False  # Oversized (>64)
    assert is_valid_request_id("invalid spaces id") is False
    assert is_valid_request_id("invalid$char!") is False
    assert is_valid_request_id("") is False
    assert is_valid_request_id(None) is False


@pytest.mark.asyncio
async def test_request_id_generated_when_missing(async_client):
    """Verifies that an incoming request without X-Request-ID receives a generated valid ID."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    assert HEADER_REQUEST_ID in res.headers
    req_id = res.headers[HEADER_REQUEST_ID]
    assert is_valid_request_id(req_id) is True
    assert len(req_id) == 32


@pytest.mark.asyncio
async def test_valid_incoming_request_id_propagated(async_client):
    """Verifies that a valid client-provided X-Request-ID is retained and returned."""
    custom_id = "client-trace-id-998877"
    res = await async_client.get("/health", headers={HEADER_REQUEST_ID: custom_id})
    assert res.status_code == 200
    assert res.headers[HEADER_REQUEST_ID] == custom_id


@pytest.mark.asyncio
async def test_invalid_incoming_request_id_replaced(async_client):
    """Verifies that an invalid/unsafe X-Request-ID is replaced with a generated secure ID."""
    malicious_id = "malicious<script>alert(1)</script>"
    res = await async_client.get("/health", headers={HEADER_REQUEST_ID: malicious_id})
    assert res.status_code == 200
    returned_id = res.headers[HEADER_REQUEST_ID]
    assert returned_id != malicious_id
    assert is_valid_request_id(returned_id) is True


@pytest.mark.asyncio
async def test_async_contextvar_isolation():
    """Verifies that concurrent asynchronous tasks do NOT leak ContextVar request IDs across tasks."""
    async def worker_task(task_id_val: str, delay_seconds: float):
        token = request_id_ctx_var.set(task_id_val)
        try:
            await asyncio.sleep(delay_seconds)
            current = get_current_request_id()
            assert current == task_id_val, f"ContextVar collision! Expected {task_id_val}, got {current}"
        finally:
            request_id_ctx_var.reset(token)

    # Launch 20 concurrent async workers with interleaving sleeps
    tasks = [
        worker_task(f"task-id-{i:03d}", 0.005 * ((i % 5) + 1))
        for i in range(20)
    ]
    await asyncio.gather(*tasks)
