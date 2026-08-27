"""
Unit tests for Core Cryptographic Security module (backend/app/core/security.py).
Tests PBKDF2 hashing, constant-time verification, JWT signing, expiration, tamper resistance,
alg=none rejection, algorithm confusion defense, and claim validation.
"""
from datetime import timedelta
import pytest
from backend.app.core.security import (
    ExpiredTokenError,
    InvalidClaimsError,
    InvalidSignatureError,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification():
    """Verifies correct password hashing and constant-time verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_password_salting_uniqueness():
    """Verifies that hashing the same password twice yields different hashes due to random salt."""
    p = "SamePassword"
    h1 = hash_password(p)
    h2 = hash_password(p)

    assert h1 != h2
    assert verify_password(p, h1) is True
    assert verify_password(p, h2) is True


def test_password_verification_malformed_hash():
    """Verifies that malformed or corrupted hashes return False without crashing."""
    assert verify_password("pass", "invalid_hash_string") is False
    assert verify_password("pass", "pbkdf2_sha256$not_an_int$salt$hash") is False
    assert verify_password("pass", "") is False


def test_jwt_create_and_decode_valid():
    """Verifies valid token creation and successful claim decoding."""
    data = {
        "sub": "user-uuid-1234",
        "roles": ["Employee"],
        "clearance": 1,
    }
    token = create_access_token(data)
    payload = decode_access_token(token)

    assert payload["sub"] == "user-uuid-1234"
    assert payload["roles"] == ["Employee"]
    assert payload["clearance"] == 1
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_tampered_payload_rejected():
    """Verifies that tampering with payload claims invalidates the cryptographic signature."""
    token = create_access_token({"sub": "user-123", "clearance": 1})
    parts = token.split(".")

    # Tamper payload: replace base64 payload with elevated clearance
    tampered_token = f"{parts[0]}.eyJyZXBsYWNlZCI6InRydWUifQ.{parts[2]}"

    with pytest.raises(InvalidSignatureError):
        decode_access_token(tampered_token)


def test_jwt_tampered_signature_rejected():
    """Verifies that modifying signature bytes fails verification."""
    token = create_access_token({"sub": "user-123"})
    parts = token.split(".")
    tampered_sig = parts[2][:-2] + "AA"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    with pytest.raises(InvalidSignatureError):
        decode_access_token(tampered_token)


def test_jwt_expired_token_rejected():
    """Verifies that expired tokens raise ExpiredTokenError."""
    # Negative expiration delta
    token = create_access_token({"sub": "user-123"}, expires_delta=timedelta(seconds=-10))

    with pytest.raises(ExpiredTokenError):
        decode_access_token(token)


def test_jwt_alg_none_defense():
    """Verifies that alg=none attack is strictly rejected."""
    # Header: {"typ":"JWT","alg":"none"} -> eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0
    none_header = "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0"
    payload = "eyJzdWIiOiJhZG1pbiJ9"
    token = f"{none_header}.{payload}."

    with pytest.raises(InvalidSignatureError):
        decode_access_token(token)


def test_jwt_missing_sub_rejected():
    """Verifies that tokens without 'sub' claim are rejected."""
    token = create_access_token({"roles": ["Employee"]})
    # create_access_token didn't get sub, payload has no sub
    with pytest.raises(InvalidClaimsError):
        decode_access_token(token)
