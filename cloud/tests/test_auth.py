"""Unit tests for JWT auth enforcement on dependency functions.

Tests verify that get_current_user, get_current_client, and
get_any_authenticated correctly accept or reject tokens based on
role, expiry, and validity.
"""

from __future__ import annotations

import pytest

jwt = pytest.importorskip("jwt", reason="PyJWT required for auth tests")

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.deps import get_any_authenticated, get_current_client, get_current_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_credentials(role: str, exp_minutes: int = 30) -> HTTPAuthorizationCredentials:
    """Build a valid HTTPAuthorizationCredentials object with the given role."""
    payload = {
        "sub": "test",
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_expired_credentials(role: str = "operator") -> HTTPAuthorizationCredentials:
    """Build credentials with an already-expired token."""
    payload = {
        "sub": "test",
        "role": role,
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_invalid_credentials() -> HTTPAuthorizationCredentials:
    """Build credentials with a completely invalid (garbage) token string."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-valid-jwt")


# ---------------------------------------------------------------------------
# get_current_user  (requires role == "operator")
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    def test_operator_token_succeeds(self):
        creds = _make_credentials("operator")
        payload = get_current_user(creds)
        assert payload["sub"] == "test"
        assert payload["role"] == "operator"

    def test_client_token_returns_403(self):
        creds = _make_credentials("client")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds)
        assert exc_info.value.status_code == 403

    def test_none_credentials_returns_401(self):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(None)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_current_client  (requires role == "client")
# ---------------------------------------------------------------------------

class TestGetCurrentClient:
    def test_client_token_succeeds(self):
        creds = _make_credentials("client")
        payload = get_current_client(creds)
        assert payload["sub"] == "test"
        assert payload["role"] == "client"

    def test_operator_token_returns_403(self):
        creds = _make_credentials("operator")
        with pytest.raises(HTTPException) as exc_info:
            get_current_client(creds)
        assert exc_info.value.status_code == 403

    def test_none_credentials_returns_401(self):
        with pytest.raises(HTTPException) as exc_info:
            get_current_client(None)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_any_authenticated  (accepts "operator" or "client")
# ---------------------------------------------------------------------------

class TestGetAnyAuthenticated:
    def test_operator_token_succeeds(self):
        creds = _make_credentials("operator")
        payload = get_any_authenticated(creds)
        assert payload["sub"] == "test"
        assert payload["role"] == "operator"

    def test_client_token_succeeds(self):
        creds = _make_credentials("client")
        payload = get_any_authenticated(creds)
        assert payload["sub"] == "test"
        assert payload["role"] == "client"

    def test_none_credentials_returns_401(self):
        with pytest.raises(HTTPException) as exc_info:
            get_any_authenticated(None)
        assert exc_info.value.status_code == 401

    def test_unknown_role_returns_403(self):
        creds = _make_credentials("admin")
        with pytest.raises(HTTPException) as exc_info:
            get_any_authenticated(creds)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Token edge cases (apply to all three dependency functions)
# ---------------------------------------------------------------------------

class TestTokenEdgeCases:
    def test_expired_token_returns_401(self):
        creds = _make_expired_credentials("operator")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_token_string_returns_401(self):
        creds = _make_invalid_credentials()
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds)
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    def test_expired_token_on_get_any_authenticated(self):
        creds = _make_expired_credentials("client")
        with pytest.raises(HTTPException) as exc_info:
            get_any_authenticated(creds)
        assert exc_info.value.status_code == 401

    def test_invalid_token_on_get_current_client(self):
        creds = _make_invalid_credentials()
        with pytest.raises(HTTPException) as exc_info:
            get_current_client(creds)
        assert exc_info.value.status_code == 401
