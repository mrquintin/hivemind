"""Integration tests for authentication endpoints."""
from __future__ import annotations

import pytest

from app.models.user import User
from app.security import hash_password


@pytest.fixture(autouse=True)
def _seed_test_users(db_session):
    """Seed test users into the database for every test in this module."""
    db_session.add(User(username="testuser", password_hash=hash_password("testpass"), role="operator"))
    db_session.add(User(username="testclient", password_hash=hash_password("clientpass"), role="client"))
    db_session.commit()


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Clear login rate limit state between tests."""
    from app.routers.auth import _failed_attempts

    _failed_attempts.clear()
    yield
    _failed_attempts.clear()


class TestLogin:
    def test_login_valid_credentials(self, client):
        res = client.post("/auth/login", json={"username": "testuser", "password": "testpass"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        res = client.post("/auth/login", json={"username": "testuser", "password": "wrong"})
        assert res.status_code == 401
        assert "Invalid credentials" in res.json()["detail"]

    def test_login_nonexistent_user(self, client):
        res = client.post("/auth/login", json={"username": "nouser", "password": "anything"})
        assert res.status_code == 401
        assert "Invalid credentials" in res.json()["detail"]

    def test_login_empty_username(self, client):
        res = client.post("/auth/login", json={"username": "", "password": "x"})
        assert res.status_code == 400

    def test_login_whitespace_username(self, client):
        res = client.post("/auth/login", json={"username": "   ", "password": "x"})
        assert res.status_code == 400

    def test_login_missing_password_field(self, client):
        res = client.post("/auth/login", json={"username": "testuser"})
        assert res.status_code == 422  # Pydantic validation error

    def test_login_case_insensitive_username(self, client):
        res = client.post("/auth/login", json={"username": "TestUser", "password": "testpass"})
        assert res.status_code == 200


class TestLoginRateLimit:
    def test_rate_limit_after_failed_attempts(self, client):
        """The 6th failed attempt within the window should return 429."""
        for i in range(5):
            res = client.post("/auth/login", json={"username": "testuser", "password": "wrong"})
            assert res.status_code == 401, f"Attempt {i+1} should return 401"

        res = client.post("/auth/login", json={"username": "testuser", "password": "wrong"})
        assert res.status_code == 429

    def test_rate_limit_does_not_block_other_users(self, client):
        """Rate limiting is per-username — other users are unaffected."""
        for _ in range(5):
            client.post("/auth/login", json={"username": "testuser", "password": "wrong"})

        res = client.post("/auth/login", json={"username": "testclient", "password": "clientpass"})
        assert res.status_code == 200


class TestAuthEnforcement:
    def test_agents_without_token_rejected(self, client):
        res = client.get("/agents")
        assert res.status_code in (401, 403)

    def test_agents_with_valid_token(self, client, operator_headers):
        res = client.get("/agents", headers=operator_headers)
        assert res.status_code == 200

    def test_agents_with_expired_token(self, client, expired_headers):
        res = client.get("/agents", headers=expired_headers)
        assert res.status_code == 401


class TestMe:
    def test_get_me_returns_identity(self, client, operator_headers):
        res = client.get("/auth/me", headers=operator_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "testuser"
        assert data["role"] == "operator"

    def test_get_me_without_token(self, client):
        res = client.get("/auth/me")
        assert res.status_code in (401, 403)


class TestRefresh:
    def test_refresh_with_valid_token(self, client, operator_headers):
        res = client.post("/auth/refresh", headers=operator_headers)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data

    def test_refresh_without_token(self, client):
        res = client.post("/auth/refresh")
        assert res.status_code in (401, 403)
