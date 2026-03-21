"""Integration tests for health check endpoints."""
from __future__ import annotations


class TestHealthCheck:
    def test_health_returns_200(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data

    def test_health_no_auth_required(self, client):
        """Health endpoint should be public."""
        res = client.get("/health")
        assert res.status_code == 200
