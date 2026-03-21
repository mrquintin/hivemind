"""Integration tests for authentication endpoints."""
from __future__ import annotations

from unittest.mock import patch


class TestLogin:
    @patch("app.routers.auth.settings")
    def test_login_valid_username(self, mock_settings, client):
        mock_settings.CLEARED_USERNAMES = ""
        mock_settings.JWT_SECRET = "change-me"
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_EXPIRES_MINUTES = 60
        mock_settings.ANTHROPIC_API_KEY = None
        res = client.post("/auth/login", json={"username": "testuser"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @patch("app.routers.auth.settings")
    def test_login_empty_username(self, mock_settings, client):
        mock_settings.CLEARED_USERNAMES = ""
        res = client.post("/auth/login", json={"username": ""})
        assert res.status_code == 400

    @patch("app.routers.auth.settings")
    def test_login_whitespace_username(self, mock_settings, client):
        mock_settings.CLEARED_USERNAMES = ""
        res = client.post("/auth/login", json={"username": "   "})
        assert res.status_code == 400

    @patch("app.routers.auth.settings")
    def test_login_non_cleared_username(self, mock_settings, client):
        mock_settings.CLEARED_USERNAMES = "admin,operator"
        res = client.post("/auth/login", json={"username": "hacker"})
        assert res.status_code == 403


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
