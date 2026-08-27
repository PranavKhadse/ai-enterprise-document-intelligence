"""
Request Correlation & Context Management.
Provides ASGI middleware and ContextVar utilities to propagate, validate,
and generate cryptographically secure correlation Request IDs (X-Request-ID)
across asynchronous request lifecycles.
"""
from contextvars import ContextVar, Token
import re
import secrets
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Regex for safe, standard Request IDs (alphanumeric, hyphens, underscores, 1-64 characters)
REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
HEADER_REQUEST_ID = "X-Request-ID"

# Global ContextVar isolated per async task
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")


def is_valid_request_id(request_id: Optional[str]) -> bool:
    """Validates that request_id contains only safe characters and is within bounds (1-64 chars)."""
    if not request_id or not isinstance(request_id, str):
        return False
    return bool(REQUEST_ID_PATTERN.fullmatch(request_id.strip()))


def generate_request_id() -> str:
    """Generates a cryptographically strong 32-character hexadecimal request ID."""
    return secrets.token_hex(16)


def get_current_request_id() -> str:
    """Retrieves the request ID for the active asynchronous execution context."""
    return request_id_ctx_var.get()


def set_current_request_id(req_id: str) -> Token:
    """Sets the request ID in the current ContextVar and returns the restoration Token."""
    return request_id_ctx_var.set(req_id)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware ensuring every HTTP request has an authoritative, sanitized correlation ID:
    1. Inspects incoming X-Request-ID header.
    2. Validates against character and length constraints; replaces invalid/missing headers with secure random IDs.
    3. Populates request.state.request_id and task-isolated ContextVar.
    4. Attaches X-Request-ID to outgoing response headers.
    5. Cleans up ContextVar upon request termination.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming_id = request.headers.get(HEADER_REQUEST_ID)

        if incoming_id and is_valid_request_id(incoming_id):
            active_request_id = incoming_id.strip()
        else:
            active_request_id = generate_request_id()

        # Attach to request state for handler access
        request.state.request_id = active_request_id

        # Bind to ContextVar for background/service access
        token = request_id_ctx_var.set(active_request_id)
        try:
            response: Response = await call_next(request)
            response.headers[HEADER_REQUEST_ID] = active_request_id
            return response
        finally:
            request_id_ctx_var.reset(token)
