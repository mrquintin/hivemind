"""Integration tests for analysis endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from hivemind_core.types import BudgetUsage, RepairStats


def _make_mock_output():
    """Create a mock HivemindOutput with all required attributes."""
    output = MagicMock()
    output.recommendations = []
    output.vetoed_solutions = []
    output.audit_trail = []
    output.debate_rounds = 2
    output.veto_restarts = 0
    output.theory_units_created = 1
    output.total_tokens = 500
    output.duration_ms = 1200
    output.termination_reason = "simple_completed"
    output.budget_usage = BudgetUsage()
    output.repair_stats = RepairStats()
    output.mode_used = "simple"
    return output


class TestAnalysisRun:
    @patch("app.routers.analysis.create_engine")
    def test_analysis_run_success(self, mock_create_engine, client, operator_headers):
        mock_engine = MagicMock()
        mock_engine.analyze.return_value = _make_mock_output()
        mock_create_engine.return_value = mock_engine

        res = client.post(
            "/analysis/run",
            json={
                "problem_statement": "Should we enter market X?",
                "analysis_mode": "simple",
                "effort_level": "low",
                "enabled_theory_agent_ids": ["agent-1"],
                "enabled_practicality_agent_ids": [],
            },
            headers=operator_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["mode_used"] == "simple"
        assert data["termination_reason"] == "simple_completed"
        assert "id" in data

    def test_analysis_run_without_auth(self, client):
        res = client.post(
            "/analysis/run",
            json={
                "problem_statement": "Test",
                "enabled_theory_agent_ids": ["agent-1"],
            },
        )
        assert res.status_code in (401, 403)

    @patch("app.routers.analysis.create_engine")
    def test_analysis_run_missing_theory_agents(self, mock_create_engine, client, operator_headers):
        """Should fail when no theory agents and no density specified."""
        res = client.post(
            "/analysis/run",
            json={
                "problem_statement": "Test problem",
                "enabled_theory_agent_ids": [],
                "enabled_practicality_agent_ids": [],
            },
            headers=operator_headers,
        )
        assert res.status_code == 400


class TestAnalysisRateLimit:
    def setup_method(self):
        """Clear rate limit state between tests."""
        from app.routers.analysis import _rate_buckets
        _rate_buckets.clear()

    @patch("app.routers.analysis.create_engine")
    def test_rate_limit_returns_429(self, mock_create_engine, client, operator_headers):
        """11th request within the window returns 429."""
        mock_engine = MagicMock()
        mock_engine.analyze.return_value = _make_mock_output()
        mock_create_engine.return_value = mock_engine

        payload = {
            "problem_statement": "Rate limit test",
            "analysis_mode": "simple",
            "effort_level": "low",
            "enabled_theory_agent_ids": ["agent-1"],
            "enabled_practicality_agent_ids": [],
        }

        # Send 10 requests — all should succeed
        for i in range(10):
            res = client.post("/analysis/run", json=payload, headers=operator_headers)
            assert res.status_code == 200, f"Request {i+1} should succeed"

        # 11th request should be rate limited
        res = client.post("/analysis/run", json=payload, headers=operator_headers)
        assert res.status_code == 429


class TestAnalysisAccessControl:
    def setup_method(self):
        from app.routers.analysis import _rate_buckets

        _rate_buckets.clear()

    @patch("app.routers.analysis.create_engine")
    def test_client_cannot_read_operator_analysis(self, mock_create_engine, client, operator_headers, client_headers):
        mock_engine = MagicMock()
        mock_engine.analyze.return_value = _make_mock_output()
        mock_create_engine.return_value = mock_engine

        create_res = client.post(
            "/analysis/run",
            json={
                "problem_statement": "operator-owned analysis",
                "enabled_theory_agent_ids": ["agent-1"],
            },
            headers=operator_headers,
        )
        assert create_res.status_code == 200
        analysis_id = create_res.json()["id"]

        get_res = client.get(f"/analysis/{analysis_id}", headers=client_headers)
        assert get_res.status_code == 404

    @patch("app.routers.analysis.create_engine")
    def test_client_can_read_own_analysis(self, mock_create_engine, client, client_headers):
        mock_engine = MagicMock()
        mock_engine.analyze.return_value = _make_mock_output()
        mock_create_engine.return_value = mock_engine

        create_res = client.post(
            "/analysis/run",
            json={
                "problem_statement": "client-owned analysis",
                "enabled_theory_agent_ids": ["agent-1"],
            },
            headers=client_headers,
        )
        assert create_res.status_code == 200
        analysis_id = create_res.json()["id"]

        get_res = client.get(f"/analysis/{analysis_id}", headers=client_headers)
        assert get_res.status_code == 200
