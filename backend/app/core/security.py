"""
Core Security and Cryptographic Utilities.
Provides PBKDF2 password hashing and HMAC-SHA256 JWT generation and validation
using Python standard library cryptography primitives with constant-time digest verification.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, Optional
from backend.app.core.config import settings


class AuthSecurityError(Exception):
    """Base exception for authentication and token security failures."""
    pass


class InvalidTokenError(AuthSecurityError):
    """Raised when a JWT token format is malformed or invalid."""
    pass


class ExpiredTokenError(AuthSecurityError):
    """Raised when a JWT token has expired."""
    pass


class InvalidSignatureError(AuthSecurityError):
    """Raised when a JWT cryptographic signature check fails or is tampered."""
    pass


class InvalidClaimsError(AuthSecurityError):
    """Raised when JWT claims (issuer, audience, subject) fail validation."""
    pass


# -----------------------------------------------------------------------------
# Base64URL Encoding Helpers
# -----------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    """Encodes bytes into standard URL-safe Base64 without '=' padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    """Decodes a URL-safe Base64 string, adding padding if missing."""
    rem = len(s) % 4
    if rem > 0:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s.encode("utf-8"))


# -----------------------------------------------------------------------------
# Password Hashing & Verification (PBKDF2-HMAC-SHA256)
# -----------------------------------------------------------------------------

def hash_password(password: str, iterations: Optional[int] = None) -> str:
    """
    Hashes a plaintext password using PBKDF2-HMAC-SHA256 with dynamic random salt.
    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    """
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string.")

    iter_count = iterations or settings.SECURITY_PASSWORD_ITERATIONS
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iter_count,
    )
    hash_hex = dk.hex()
    return f"pbkdf2_sha256${iter_count}${salt}${hash_hex}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored PBKDF2 hash using constant-time comparison.
    Never raises an unhandled exception on malformed hashes.
    """
    if not plain_password or not hashed_password or not isinstance(hashed_password, str):
        return False

    parts = hashed_password.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False

    try:
        iter_count = int(parts[1])
        salt = parts[2]
        expected_hash = parts[3]

        candidate_dk = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iter_count,
        )
        candidate_hex = candidate_dk.hex()

        # Constant-time comparison
        return hmac.compare_digest(candidate_hex, expected_hash)
    except Exception:
        return False


# -----------------------------------------------------------------------------
# JWT Generation & Cryptographic Validation (HS256)
# -----------------------------------------------------------------------------

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Creates a signed JWT access token using HMAC-SHA256 with standard claims.
    """
    secret = secret_key or settings.JWT_SECRET_KEY
    if not secret or len(secret) < 16:
        raise ValueError("JWT_SECRET_KEY must be configured with at least 16 characters.")

    algorithm = settings.JWT_ALGORITHM
    if algorithm != "HS256":
        raise ValueError(f"Unsupported JWT algorithm: {algorithm}. Only HS256 is supported.")

    header = {
        "typ": "JWT",
        "alg": algorithm,
    }

    now = datetime.now(timezone.utc)
    expire_duration = expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    exp = now + expire_duration

    payload = {
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": secrets.token_hex(16),
        "token_version": 1,
    }
    # Merge custom user claims
    payload.update(data)

    # Ensure timestamps are integers
    if isinstance(payload.get("exp"), datetime):
        payload["exp"] = int(payload["exp"].timestamp())
    if isinstance(payload.get("iat"), datetime):
        payload["iat"] = int(payload["iat"].timestamp())

    b64_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    b64_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{b64_header}.{b64_payload}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    b64_sig = _b64url_encode(sig)

    return f"{b64_header}.{b64_payload}.{b64_sig}"


def decode_access_token(
    token: str,
    secret_key: Optional[str] = None,
    verify_exp: bool = True,
    verify_claims: bool = True,
) -> Dict[str, Any]:
    """
    Validates cryptographic signature, algorithm, expiration, issuer, and audience of a JWT.
    Raises structured security exceptions on tamper, expiration, or invalid format.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("JWT token must be a non-empty string.")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Malformed JWT token: must contain exactly 3 dot-separated segments.")

    b64_header, b64_payload, b64_sig = parts

    # 1. Parse and validate header
    try:
        header_bytes = _b64url_decode(b64_header)
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as e:
        raise InvalidTokenError(f"Failed to parse JWT header: {str(e)}")

    alg = header.get("alg")
    if not alg or alg.lower() == "none" or alg != settings.JWT_ALGORITHM:
        raise InvalidSignatureError(f"Rejected unapproved or mismatched algorithm: '{alg}'. Only {settings.JWT_ALGORITHM} is permitted.")

    # 2. Cryptographic signature verification BEFORE trusting payload
    secret = secret_key or settings.JWT_SECRET_KEY
    signing_input = f"{b64_header}.{b64_payload}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()

    try:
        provided_sig = _b64url_decode(b64_sig)
    except Exception:
        raise InvalidSignatureError("Malformed signature encoding.")

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise InvalidSignatureError("Cryptographic JWT signature verification failed.")

    # 3. Parse payload
    try:
        payload_bytes = _b64url_decode(b64_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise InvalidTokenError(f"Failed to parse JWT payload: {str(e)}")

    now_ts = int(datetime.now(timezone.utc).timestamp())

    # 4. Expiration validation
    if verify_exp:
        exp = payload.get("exp")
        if exp is None:
            raise InvalidClaimsError("Missing mandatory 'exp' claim.")
        if now_ts > int(exp):
            raise ExpiredTokenError("JWT token has expired.")

    # 5. Claims validation (Subject, Issuer, Audience)
    if verify_claims:
        if not payload.get("sub"):
            raise InvalidClaimsError("Missing mandatory 'sub' (subject) claim.")

        iss = payload.get("iss")
        if iss and iss != settings.JWT_ISSUER:
            raise InvalidClaimsError(f"Invalid issuer: expected '{settings.JWT_ISSUER}', got '{iss}'.")

        aud = payload.get("aud")
        if aud and aud != settings.JWT_AUDIENCE:
            raise InvalidClaimsError(f"Invalid audience: expected '{settings.JWT_AUDIENCE}', got '{aud}'.")

    return payload
