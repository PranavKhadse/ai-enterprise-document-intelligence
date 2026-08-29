"""
Phase 11 Audit Logging, Security Observability & Compliance Service.
Provides authoritative, append-only audit persistence, recursive secret redaction,
query fingerprinting, tamper-evident hash chaining, and administrative query analytics.
"""
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.request_context import get_current_request_id
from backend.app.db.models.audit_event import AuditEvent
from backend.app.db.models.user import User
from backend.app.db.session import AsyncSessionLocal
from backend.app.schemas.audit import (
    AuditEventCreate,
    AuditEventResponse,
    AuditEventType,
    AuditQueryFilter,
    AuditSeverity,
    AuditStatisticsResponse,
    AuthorizationResult,
)
from backend.app.schemas.auth import RBACContext

logger = logging.getLogger(__name__)

# Substrings that trigger automated value redaction
REDACTION_SUBSTRINGS: Set[str] = {
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "private_key",
    "access_token",
    "refresh_token",
    "cookie",
    "session",
    "client_secret",
}

# Regex patterns for detecting embedded JWT tokens and Bearer credentials in string values
JWT_STRING_PATTERN = re.compile(r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+")
BEARER_STRING_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]+", re.IGNORECASE)


def is_sensitive_key(key_name: str) -> bool:
    """Checks whether a dictionary key matches any sensitive security keywords."""
    if not isinstance(key_name, str):
        return False
    lower = key_name.lower().replace("-", "_")
    return any(sub in lower for sub in REDACTION_SUBSTRINGS)


def sanitize_metadata(
    data: Any,
    max_size_bytes: int = settings.AUDIT_MAX_METADATA_SIZE,
    current_depth: int = 0,
    max_depth: int = 15,
) -> Any:
    """
    Recursively cleans and redacts sensitive data from metadata dictionaries and collections.
    - Redacts password, secret, token, and credential keys to '[REDACTED]'.
    - Sanitizes embedded JWT / Bearer strings.
    - Converts non-JSON types (UUID, datetime, Enum) to safe primitives.
    - Enforces depth and size constraints to prevent unbounded payload expansion.
    """
    if current_depth > max_depth:
        return "[TRUNCATED: MAX_DEPTH]"

    if data is None:
        return None

    if isinstance(data, (int, float, bool)):
        return data

    if isinstance(data, uuid.UUID):
        return str(data)

    if isinstance(data, datetime):
        return data.isoformat()

    if isinstance(data, Enum):
        return data.value

    if isinstance(data, str):
        # Sanitize embedded Bearer headers first
        sanitized_str = BEARER_STRING_PATTERN.sub("Bearer [REDACTED]", data)
        # Sanitize remaining standalone embedded JWT strings
        sanitized_str = JWT_STRING_PATTERN.sub("[REDACTED_JWT]", sanitized_str)
        return sanitized_str

    if isinstance(data, dict):
        cleaned_dict: Dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            if is_sensitive_key(key_str):
                cleaned_dict[key_str] = "[REDACTED]"
            else:
                cleaned_dict[key_str] = sanitize_metadata(
                    v, max_size_bytes=max_size_bytes, current_depth=current_depth + 1, max_depth=max_depth
                )
        return cleaned_dict

    if isinstance(data, (list, tuple, set)):
        return [
            sanitize_metadata(item, max_size_bytes=max_size_bytes, current_depth=current_depth + 1, max_depth=max_depth)
            for item in data
        ]

    # Fallback for arbitrary objects
    try:
        return str(data)
    except Exception:
        return "[UNSERIALIZABLE]"


def generate_query_fingerprint(query: Optional[str]) -> Optional[str]:
    """
    Generates a deterministic, one-way SHA-256 fingerprint for search and RAG queries.
    Enforces privacy by ensuring identical normalized queries yield identical hashes without storing raw text.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return None
    normalized = re.sub(r"\s+", " ", query.strip().lower())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _normalize_dt_str(created_at: Union[str, datetime]) -> str:
    """Normalizes datetime to a canonical ISO format resilient to microsecond/database storage differences."""
    if isinstance(created_at, datetime):
        return created_at.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(created_at, str):
        try:
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            return created_at[:19]
    return str(created_at)


def compute_canonical_event_hash(
    event_id: Union[str, uuid.UUID],
    created_at: Union[str, datetime],
    request_id: Optional[str],
    event_type: str,
    severity: str,
    user_id: Optional[Union[str, uuid.UUID]],
    action: str,
    resource_type: Optional[str],
    resource_id: Optional[str],
    authorization_result: str,
    query_fingerprint: Optional[str],
    previous_event_hash: Optional[str] = None,
) -> str:
    """
    Computes a canonical SHA-256 hash across core audit attributes for tamper-evident integrity chaining.
    """
    dt_str = _normalize_dt_str(created_at)
    components = [
        str(event_id),
        dt_str,
        str(request_id or ""),
        str(event_type),
        str(severity),
        str(user_id or ""),
        str(action),
        str(resource_type or ""),
        str(resource_id or ""),
        str(authorization_result),
        str(query_fingerprint or ""),
        str(previous_event_hash or "GENESIS"),
    ]
    raw_payload = "|".join(components)
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


class AuditService:
    """
    Authoritative server-side audit logging, tamper-evident hash chaining, and security observability service.
    """

    @staticmethod
    def extract_principal_info(
        principal: Optional[Union[User, RBACContext, Dict[str, Any]]] = None,
    ) -> Tuple[Optional[uuid.UUID], Optional[str], Optional[uuid.UUID], List[str], Optional[int]]:
        """
        Extracts verified actor identity from server-authoritative Phase 10 objects.
        Returns: (user_id, email, department_id, roles, clearance_level)
        """
        if principal is None:
            return None, None, None, [], None

        if isinstance(principal, User):
            roles = [r.name for r in (principal.roles or [])] or ["Employee"]
            clearance = max(
                (1 if r == "Employee" else 2 if r == "HR_Manager" else 3 if r == "Legal" else 4 for r in roles),
                default=1,
            )
            return principal.id, principal.email, principal.department_id, roles, clearance

        if isinstance(principal, RBACContext):
            return (
                principal.user_id,
                principal.email,
                principal.department_id,
                principal.roles,
                principal.clearance_level,
            )

        if isinstance(principal, dict):
            return (
                principal.get("user_id"),
                principal.get("email"),
                principal.get("department_id"),
                principal.get("roles", []),
                principal.get("clearance_level"),
            )

        return None, None, None, [], None

    async def _get_latest_event_hash(self, db: AsyncSession) -> Optional[str]:
        """Retrieves the hash of the most recent audit event for chaining."""
        try:
            if db.in_transaction():
                async with db.begin_nested():
                    stmt = (
                        select(AuditEvent.event_hash)
                        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                        .limit(1)
                    )
                    res = await db.execute(stmt)
                    return res.scalar_one_or_none()
            else:
                stmt = (
                    select(AuditEvent.event_hash)
                    .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                    .limit(1)
                )
                res = await db.execute(stmt)
                return res.scalar_one_or_none()
        except Exception as err:
            logger.debug("Could not retrieve latest audit event hash: %s", err)
            return None

    async def record_event(
        self,
        event_type: Union[AuditEventType, str],
        action: str,
        severity: Union[AuditSeverity, str] = AuditSeverity.INFO,
        principal: Optional[Union[User, RBACContext, Dict[str, Any]]] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        authorization_result: Union[AuthorizationResult, str] = AuthorizationResult.ALLOWED,
        request_id: Optional[str] = None,
        http_method: Optional[str] = None,
        api_path: Optional[str] = None,
        status_code: Optional[int] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        raw_query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """
        Creates and persists a structured audit event.
        Guarantees:
        - Server-authoritative actor resolution
        - Recursive secret redaction
        - Privacy-safe query fingerprinting
        - Tamper-evident hash chaining
        - Isolation: failures will not crash the primary business flow
        """
        if not settings.AUDIT_ENABLED:
            return None

        # Resolve request ID
        active_req_id = request_id or get_current_request_id() or None

        # Extract authoritative principal info
        user_id, email, dept_id, roles, clearance = self.extract_principal_info(principal)

        # Normalize enums/strings
        e_type = event_type.value if isinstance(event_type, Enum) else str(event_type)
        e_sev = severity.value if isinstance(severity, Enum) else str(severity)
        authz_res = authorization_result.value if isinstance(authorization_result, Enum) else str(authorization_result)

        # Sanitize metadata payload
        meta_payload = deepcopy(metadata) if metadata else {}
        if settings.AUDIT_STORE_QUERY_TEXT and raw_query:
            # Only store query text if explicitly enabled in configuration
            safe_query = raw_query[:settings.AUDIT_MAX_QUERY_TEXT_LENGTH]
            meta_payload["query_text_snippet"] = safe_query

        sanitized_meta = sanitize_metadata(meta_payload)
        q_fingerprint = generate_query_fingerprint(raw_query)

        event_id = uuid.uuid4()
        now_dt = datetime.now(timezone.utc)

        # Internal helper to persist event into provided or new session
        async def _persist(session: AsyncSession) -> AuditEvent:
            prev_hash = None
            if settings.AUDIT_HASH_CHAIN_ENABLED:
                prev_hash = await self._get_latest_event_hash(session)

            computed_hash = None
            if settings.AUDIT_HASH_CHAIN_ENABLED:
                computed_hash = compute_canonical_event_hash(
                    event_id=event_id,
                    created_at=now_dt,
                    request_id=active_req_id,
                    event_type=e_type,
                    severity=e_sev,
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    authorization_result=authz_res,
                    query_fingerprint=q_fingerprint,
                    previous_event_hash=prev_hash,
                )

            event = AuditEvent(
                id=event_id,
                created_at=now_dt,
                request_id=active_req_id,
                event_type=e_type,
                severity=e_sev,
                user_id=user_id,
                email=email,
                department_id=dept_id,
                roles=roles,
                clearance_level=clearance,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                authorization_result=authz_res,
                http_method=http_method,
                api_path=api_path,
                status_code=status_code,
                source_ip=source_ip,
                user_agent=user_agent,
                query_fingerprint=q_fingerprint,
                event_hash=computed_hash,
                previous_event_hash=prev_hash,
                metadata_json=sanitized_meta,
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return event

        try:
            if db is not None:
                try:
                    return await _persist(db)
                except Exception as db_err:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    logger.error("Audit persistence error on session: %s", db_err, exc_info=False)
                    return None
            else:
                async with AsyncSessionLocal() as session:
                    try:
                        return await _persist(session)
                    except Exception as sess_err:
                        try:
                            await session.rollback()
                        except Exception:
                            pass
                        logger.error("Audit persistence error on standalone session: %s", sess_err, exc_info=False)
                        return None
        except Exception as err:
            logger.error("Audit persistence error: %s", err, exc_info=False)
            return None

    # -------------------------------------------------------------------------
    # Domain Event Helper Methods
    # -------------------------------------------------------------------------

    async def record_auth_success(
        self,
        user: User,
        request_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """Records successful user authentication."""
        return await self.record_event(
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            action="user_login_success",
            severity=AuditSeverity.INFO,
            principal=user,
            resource_type="user",
            resource_id=str(user.id),
            authorization_result=AuthorizationResult.ALLOWED,
            request_id=request_id,
            http_method="POST",
            api_path="/api/v1/auth/login",
            status_code=200,
            source_ip=source_ip,
            user_agent=user_agent,
            metadata={"email": user.email},
            db=db,
        )

    async def record_auth_failure(
        self,
        attempted_email: str,
        reason: str = "Invalid credentials",
        request_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """Records failed authentication attempt without storing plaintext passwords."""
        return await self.record_event(
            event_type=AuditEventType.AUTH_LOGIN_FAILURE,
            action="user_login_failed",
            severity=AuditSeverity.WARNING,
            principal=None,
            resource_type="user",
            resource_id=attempted_email.strip().lower() if attempted_email else "unknown",
            authorization_result=AuthorizationResult.DENIED,
            request_id=request_id,
            http_method="POST",
            api_path="/api/v1/auth/login",
            status_code=401,
            source_ip=source_ip,
            user_agent=user_agent,
            metadata={"attempted_email": attempted_email, "failure_reason": reason},
            db=db,
        )

    async def record_authorization_denied(
        self,
        principal: Optional[Union[User, RBACContext, Dict[str, Any]]],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        reason: str = "Forbidden",
        request_id: Optional[str] = None,
        api_path: Optional[str] = None,
        http_method: Optional[str] = None,
        status_code: int = 403,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """Records an authorization denial or access restriction enforcement."""
        return await self.record_event(
            event_type=AuditEventType.AUTHORIZATION_DENIED,
            action=action,
            severity=AuditSeverity.HIGH,
            principal=principal,
            resource_type=resource_type,
            resource_id=resource_id,
            authorization_result=AuthorizationResult.DENIED,
            request_id=request_id,
            http_method=http_method,
            api_path=api_path,
            status_code=status_code,
            source_ip=source_ip,
            user_agent=user_agent,
            metadata={"denial_reason": reason},
            db=db,
        )

    async def record_document_event(
        self,
        event_type: AuditEventType,
        action: str,
        document_id: str,
        principal: Optional[Union[User, RBACContext, Dict[str, Any]]] = None,
        title: Optional[str] = None,
        file_hash: Optional[str] = None,
        department_id: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """Records document lifecycle events (created, read, compared, deleted)."""
        meta = metadata.copy() if metadata else {}
        if title:
            meta["title"] = title
        if file_hash:
            meta["file_hash"] = file_hash
        if department_id:
            meta["department_id"] = str(department_id)

        return await self.record_event(
            event_type=event_type,
            action=action,
            severity=AuditSeverity.INFO,
            principal=principal,
            resource_type="document",
            resource_id=document_id,
            authorization_result=AuthorizationResult.ALLOWED,
            request_id=request_id,
            metadata=meta,
            db=db,
        )

    async def record_rag_event(
        self,
        query: str,
        principal: Optional[Union[User, RBACContext, Dict[str, Any]]] = None,
        citations_count: int = 0,
        grounding_status: str = "fully_grounded",
        latency_ms: float = 0.0,
        request_id: Optional[str] = None,
        degraded_mode: bool = False,
        conflicts_detected: bool = False,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """Records grounded RAG queries with query fingerprint and performance metadata."""
        meta = {
            "citations_count": citations_count,
            "grounding_status": grounding_status,
            "latency_ms": round(latency_ms, 2),
            "degraded_mode": degraded_mode,
            "conflicts_detected": conflicts_detected,
        }
        return await self.record_event(
            event_type=AuditEventType.RAG_QUERY,
            action="rag_document_query",
            severity=AuditSeverity.INFO,
            principal=principal,
            resource_type="rag_pipeline",
            resource_id="grounded_synthesis",
            authorization_result=AuthorizationResult.ALLOWED,
            request_id=request_id,
            raw_query=query,
            metadata=meta,
            db=db,
        )

    async def record_comparison_event(
        self,
        doc_a_id: str,
        doc_b_id: str,
        principal: Optional[Union[User, RBACContext, Dict[str, Any]]] = None,
        divergence_index: float = 0.0,
        conflicts_count: int = 0,
        latency_ms: float = 0.0,
        request_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditEvent]:
        """Records document comparison executions and detected divergence."""
        meta = {
            "document_a_id": doc_a_id,
            "document_b_id": doc_b_id,
            "divergence_index": divergence_index,
            "conflicts_count": conflicts_count,
            "latency_ms": round(latency_ms, 2),
        }
        return await self.record_event(
            event_type=AuditEventType.DOCUMENT_COMPARED,
            action="compare_document_versions",
            severity=AuditSeverity.INFO if conflicts_count == 0 else AuditSeverity.WARNING,
            principal=principal,
            resource_type="document_diff",
            resource_id=f"{doc_a_id}:{doc_b_id}",
            authorization_result=AuthorizationResult.ALLOWED,
            request_id=request_id,
            metadata=meta,
            db=db,
        )

    # -------------------------------------------------------------------------
    # Query & Analytics Methods
    # -------------------------------------------------------------------------

    async def query_events(
        self,
        filter_spec: AuditQueryFilter,
        db: AsyncSession,
    ) -> Tuple[List[AuditEvent], int]:
        """
        Executes safe, parameterized, paginated querying across audit records.
        """
        conditions = []

        if filter_spec.event_type:
            conditions.append(AuditEvent.event_type == filter_spec.event_type.value)
        if filter_spec.severity:
            conditions.append(AuditEvent.severity == filter_spec.severity.value)
        if filter_spec.user_id:
            conditions.append(AuditEvent.user_id == filter_spec.user_id)
        if filter_spec.request_id:
            conditions.append(AuditEvent.request_id == filter_spec.request_id.strip())
        if filter_spec.resource_type:
            conditions.append(AuditEvent.resource_type == filter_spec.resource_type.strip())
        if filter_spec.resource_id:
            conditions.append(AuditEvent.resource_id == filter_spec.resource_id.strip())
        if filter_spec.authorization_result:
            conditions.append(AuditEvent.authorization_result == filter_spec.authorization_result.value)
        if filter_spec.start_time:
            conditions.append(AuditEvent.created_at >= filter_spec.start_time)
        if filter_spec.end_time:
            conditions.append(AuditEvent.created_at <= filter_spec.end_time)

        # Count total matching
        count_stmt = select(func.count(AuditEvent.id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        count_res = await db.execute(count_stmt)
        total = count_res.scalar_one()

        # Bounded query
        bounded_limit = min(max(filter_spec.limit, 1), settings.AUDIT_MAX_QUERY_LIMIT)
        bounded_offset = max(filter_spec.offset, 0)

        query_stmt = select(AuditEvent)
        if conditions:
            query_stmt = query_stmt.where(*conditions)
        query_stmt = query_stmt.order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
        query_stmt = query_stmt.limit(bounded_limit).offset(bounded_offset)

        res = await db.execute(query_stmt)
        items = list(res.scalars().all())

        return items, total

    async def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        db: Optional[AsyncSession] = None,
    ) -> AuditStatisticsResponse:
        """
        Calculates aggregate security and operational telemetry for admin compliance review.
        """
        async def _calculate(session: AsyncSession) -> AuditStatisticsResponse:
            conditions = []
            if start_time:
                conditions.append(AuditEvent.created_at >= start_time)
            if end_time:
                conditions.append(AuditEvent.created_at <= end_time)

            # Total events
            tot_stmt = select(func.count(AuditEvent.id))
            if conditions:
                tot_stmt = tot_stmt.where(*conditions)
            tot_res = await session.execute(tot_stmt)
            total_events = tot_res.scalar_one()

            # Breakdown by event_type
            type_stmt = select(AuditEvent.event_type, func.count(AuditEvent.id))
            if conditions:
                type_stmt = type_stmt.where(*conditions)
            type_stmt = type_stmt.group_by(AuditEvent.event_type)
            type_res = await session.execute(type_stmt)
            events_by_type = {row[0]: row[1] for row in type_res.all()}

            # Breakdown by severity
            sev_stmt = select(AuditEvent.severity, func.count(AuditEvent.id))
            if conditions:
                sev_stmt = sev_stmt.where(*conditions)
            sev_stmt = sev_stmt.group_by(AuditEvent.severity)
            sev_res = await session.execute(sev_stmt)
            events_by_severity = {row[0]: row[1] for row in sev_res.all()}

            # Authorization denials
            denials = events_by_type.get(AuditEventType.AUTHORIZATION_DENIED.value, 0)

            # Authentication failures
            auth_failures = events_by_type.get(AuditEventType.AUTH_LOGIN_FAILURE.value, 0)

            # Active users
            user_stmt = select(func.count(func.distinct(AuditEvent.user_id)))
            if conditions:
                user_stmt = user_stmt.where(*conditions)
            user_stmt = user_stmt.where(AuditEvent.user_id.is_not(None))
            user_res = await session.execute(user_stmt)
            active_users = user_res.scalar_one()

            # Unique resources
            res_stmt = select(func.count(func.distinct(AuditEvent.resource_id)))
            if conditions:
                res_stmt = res_stmt.where(*conditions)
            res_stmt = res_stmt.where(AuditEvent.resource_id.is_not(None))
            res_res = await session.execute(res_stmt)
            unique_resources = res_res.scalar_one()

            return AuditStatisticsResponse(
                total_events=total_events,
                events_by_type=events_by_type,
                events_by_severity=events_by_severity,
                authorization_denials=denials,
                authentication_failures=auth_failures,
                active_users_with_events=active_users,
                unique_resources_accessed=unique_resources,
                time_window_start=start_time,
                time_window_end=end_time,
            )

        if db is not None:
            return await _calculate(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _calculate(session)

    def verify_audit_log_chain(self, events: List[AuditEvent]) -> Tuple[bool, List[str]]:
        """
        Verifies tamper-evident integrity chaining across an ordered list of audit records.
        Returns (is_valid, list_of_detected_violations).
        """
        if not events:
            return True, []

        violations: List[str] = []
        # Sort chronologically for verification
        sorted_events = sorted(events, key=lambda e: (e.created_at, e.id))

        for idx, event in enumerate(sorted_events):
            expected_prev = sorted_events[idx - 1].event_hash if idx > 0 else None
            if idx > 0 and event.previous_event_hash != expected_prev:
                violations.append(
                    f"Event {event.id} previous_event_hash mismatch. Expected '{expected_prev}', got '{event.previous_event_hash}'."
                )

            computed = compute_canonical_event_hash(
                event_id=event.id,
                created_at=event.created_at,
                request_id=event.request_id,
                event_type=event.event_type,
                severity=event.severity,
                user_id=event.user_id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                authorization_result=event.authorization_result,
                query_fingerprint=event.query_fingerprint,
                previous_event_hash=event.previous_event_hash,
            )

            if event.event_hash != computed:
                violations.append(
                    f"Event {event.id} integrity failure: recorded hash '{event.event_hash}' does not match computed hash '{computed}'."
                )

        return len(violations) == 0, violations


# Global singleton instance
audit_service = AuditService()
