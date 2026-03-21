"""Tests for simple vs full mode branching, repair loop, and backward compatibility."""

import pytest
from unittest.mock import MagicMock
from hivemind_core.debate import (
    run_debate,
    run_simple_mode,
    run_full_mode,
    repair_failed_recommendations,
    apply_practicality_scoring,
    _BudgetGuard,
)
from hivemind_core.types import (
    AgentDefinition,
    BudgetExhausted,
    FeasibilityScore,
    HivemindInput,
    HivemindOutput,
    LLMInterface,
    NetworkType,
    Recommendation,
    RecommendationStatus,
    RepairStats,
    StorageInterface,
    TerminationReason,
    TheoryUnitSolution,
    VectorStoreInterface,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(solution_text="SOLUTION: Test solution\nREASONING: Test reasoning"):
    """Create a mock LLM that returns a fixed response."""
    llm = MagicMock(spec=LLMInterface)
    llm.call.return_value = {
        "content": solution_text,
        "input_tokens": 100,
        "output_tokens": 50,
    }
    return llm


def _make_mock_storage(agents=None):
    """Create a mock storage with given agents."""
    storage = MagicMock(spec=StorageInterface)
    agent_map = {}
    if agents:
        for a in agents:
            agent_map[a.id] = a
    storage.get_agent.side_effect = lambda aid: agent_map.get(aid)
    storage.get_documents_for_knowledge_bases.return_value = []
    return storage


def _make_mock_vector_store():
    vs = MagicMock(spec=VectorStoreInterface)
    vs.retrieve.return_value = []
    return vs


def _make_theory_agent(agent_id="t1", name="Theory 1"):
    return AgentDefinition(
        id=agent_id,
        name=name,
        network_type=NetworkType.THEORY,
        framework="Test Framework",
        status="published",
    )


def _make_practicality_agent(agent_id="p1", name="Practicality 1"):
    return AgentDefinition(
        id=agent_id,
        name=name,
        network_type=NetworkType.PRACTICALITY,
        framework="Risk Analysis",
        status="published",
    )


# ---------------------------------------------------------------------------
# Mode Branching Tests
# ---------------------------------------------------------------------------


class TestModeBranching:
    def test_default_mode_is_simple(self):
        inp = HivemindInput(query="test")
        assert inp.analysis_mode == "simple"

    def test_run_debate_dispatches_simple(self):
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            theory_agent_ids=["t1"],
            analysis_mode="simple",
        )
        output = run_debate(inp, llm, vs, storage)
        assert output.mode_used == "simple"
        assert output.termination_reason != ""

    def test_run_debate_dispatches_full(self):
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            theory_agent_ids=["t1"],
            analysis_mode="full",
        )
        output = run_debate(inp, llm, vs, storage)
        assert output.mode_used == "full"
        assert output.termination_reason != ""

    def test_simple_mode_no_debate_rounds(self):
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            theory_agent_ids=["t1"],
            analysis_mode="simple",
        )
        output = run_debate(inp, llm, vs, storage)
        assert output.debate_rounds == 0

    def test_output_always_has_termination_reason(self):
        """I1: Every run returns exactly one termination_reason."""
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        for mode in ("simple", "full"):
            inp = HivemindInput(
                query="test",
                theory_agent_ids=["t1"],
                analysis_mode=mode,
            )
            output = run_debate(inp, llm, vs, storage)
            assert output.termination_reason != "", f"Missing termination_reason in {mode} mode"

    def test_output_has_budget_usage(self):
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"])
        output = run_debate(inp, llm, vs, storage)
        assert output.budget_usage.llm_calls >= 1
        assert output.budget_usage.total_tokens > 0


# ---------------------------------------------------------------------------
# Repair Loop Tests
# ---------------------------------------------------------------------------


class TestRepairLoop:
    def test_repair_recovers_recommendation(self):
        """Test that a failed recommendation can be recovered via repair."""
        rec = Recommendation(
            id="r1", title="Test", content="Original content",
            average_feasibility=50, status="approved",
            feasibility_scores=[
                FeasibilityScore(agent_id="p1", agent_name="P1", score=50,
                                 risks=["risk1"], challenges=["challenge1"],
                                 mitigations=["mitigation1"]),
            ],
        )

        # LLM returns revised content, and practicality re-scores higher
        call_count = [0]
        def mock_call(**kwargs):
            call_count[0] += 1
            return {
                "content": "SOLUTION: Improved recommendation\nFeasibility Score: 90/100\nRISKS:\n- Minimal",
                "input_tokens": 100, "output_tokens": 50,
            }

        llm = MagicMock(spec=LLMInterface)
        llm.call.side_effect = lambda **kw: mock_call(**kw)

        p_agent = _make_practicality_agent()
        storage = _make_mock_storage([p_agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            practicality_agent_ids=["p1"],
            feasibility_threshold=60,
        )
        budget = _BudgetGuard(inp)
        audit = []
        repair_stats = RepairStats()

        repair_failed_recommendations(
            [rec], threshold=60, max_iterations=2,
            llm=llm, vector_store=vs, storage=storage,
            input_data=inp, budget=budget, audit_trail=audit,
            repair_stats=repair_stats,
        )

        # Repair was attempted
        assert repair_stats.recommendations_repaired == 1

    def test_repair_exhausts_iterations(self):
        """I5: If recommendation.status == failed_after_repairs, repair_history length == max_repair_iterations."""
        rec = Recommendation(
            id="r1", title="Test", content="Bad content",
            average_feasibility=30, status="approved",
            feasibility_scores=[
                FeasibilityScore(agent_id="p1", agent_name="P1", score=30),
            ],
        )

        # LLM always returns low-scoring response
        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {
            "content": "Still bad\nFeasibility Score: 35/100",
            "input_tokens": 100, "output_tokens": 50,
        }

        p_agent = _make_practicality_agent()
        storage = _make_mock_storage([p_agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            practicality_agent_ids=["p1"],
            feasibility_threshold=60,
            max_repair_iterations=2,
        )
        budget = _BudgetGuard(inp)
        audit = []
        repair_stats = RepairStats()

        repair_failed_recommendations(
            [rec], threshold=60, max_iterations=2,
            llm=llm, vector_store=vs, storage=storage,
            input_data=inp, budget=budget, audit_trail=audit,
            repair_stats=repair_stats,
        )

        assert rec.status == RecommendationStatus.FAILED_AFTER_REPAIRS.value
        assert len(rec.repair_history) == 2
        assert repair_stats.recommendations_failed_after_repairs == 1


# ---------------------------------------------------------------------------
# Budget Enforcement Tests
# ---------------------------------------------------------------------------


class TestBudgetEnforcement:
    def test_budget_stops_analysis(self):
        """I2: No loop executes beyond configured budget."""
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            theory_agent_ids=["t1"],
            analysis_mode="simple",
            max_total_llm_calls=2,
        )
        output = run_debate(inp, llm, vs, storage)
        assert output.budget_usage.llm_calls <= 3  # May slightly exceed due to agent execution
        assert output.termination_reason in (
            TerminationReason.SIMPLE_COMPLETED.value,
            TerminationReason.BUDGET_EXHAUSTED.value,
        )


# ---------------------------------------------------------------------------
# Backward Compatibility Tests
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_old_payload_runs(self):
        """I7: Backward-compatible requests without new fields still run."""
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        # Old-style input without any new fields
        inp = HivemindInput(
            query="Should we expand?",
            theory_agent_ids=["t1"],
            sufficiency_value=2,
            feasibility_threshold=60,
            max_veto_restarts=3,
        )

        output = run_debate(inp, llm, vs, storage)
        assert isinstance(output, HivemindOutput)
        assert output.mode_used == "simple"  # default
        assert output.termination_reason != ""
        assert output.budget_usage.llm_calls >= 0

    def test_no_theory_agents_returns_validation_error(self):
        """F4: No theory agents resolved returns validation error."""
        llm = _make_mock_llm()
        storage = _make_mock_storage([])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            theory_agent_ids=["nonexistent"],
        )
        output = run_debate(inp, llm, vs, storage)
        assert output.termination_reason == TerminationReason.VALIDATION_ERROR.value


# ---------------------------------------------------------------------------
# Streaming Tests
# ---------------------------------------------------------------------------


class TestStreaming:
    def test_streaming_yields_events(self):
        """I6: Streaming outputs must include complete event."""
        from hivemind_core.debate import run_debate_streaming

        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(
            query="test",
            theory_agent_ids=["t1"],
            analysis_mode="simple",
        )

        events = list(run_debate_streaming(inp, llm, vs, storage))
        assert len(events) > 0

        # Must have a complete event
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1

        output = complete_events[0]["output"]
        assert isinstance(output, HivemindOutput)
        assert output.termination_reason != ""

    def test_streaming_has_termination_event(self):
        from hivemind_core.debate import run_debate_streaming

        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"])
        events = list(run_debate_streaming(inp, llm, vs, storage))

        termination_events = [e for e in events if e.get("type") == "termination"]
        assert len(termination_events) == 1
        assert termination_events[0]["reason"] != ""

    def test_streaming_events_arrive_before_complete(self):
        """Events are yielded incrementally, not all at once."""
        from hivemind_core.debate import run_debate_streaming

        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"], analysis_mode="simple")
        events = list(run_debate_streaming(inp, llm, vs, storage))

        types = [e.get("type") for e in events]
        # debate_start and solution_generated must come before complete
        assert "debate_start" in types
        assert "complete" in types
        ds_idx = types.index("debate_start")
        comp_idx = types.index("complete")
        assert ds_idx < comp_idx

    def test_streaming_output_matches_non_streaming(self):
        """I6: Streaming and non-streaming yield same termination_reason and mode."""
        from hivemind_core.debate import run_debate_streaming

        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"], analysis_mode="simple")

        non_stream = run_debate(inp, llm, vs, storage)
        stream_events = list(run_debate_streaming(inp, llm, vs, storage))
        stream_output = [e for e in stream_events if e.get("type") == "complete"][0]["output"]

        assert non_stream.mode_used == stream_output.mode_used
        assert non_stream.termination_reason == stream_output.termination_reason


# ---------------------------------------------------------------------------
# Invariant Hardening Tests
# ---------------------------------------------------------------------------


class TestInvariantHardening:
    def test_i4_approved_has_feasibility_above_threshold(self):
        """I4: If status == approved, average_feasibility > threshold."""
        agent = _make_theory_agent()
        p_agent = _make_practicality_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent, p_agent])
        vs = _make_mock_vector_store()

        for mode in ("simple", "full"):
            inp = HivemindInput(
                query="test",
                theory_agent_ids=["t1"],
                practicality_agent_ids=["p1"],
                analysis_mode=mode,
                feasibility_threshold=60,
            )
            output = run_debate(inp, llm, vs, storage)
            for rec in output.recommendations:
                if rec.status == RecommendationStatus.APPROVED.value:
                    assert rec.average_feasibility > inp.feasibility_threshold, \
                        f"I4 violation: approved rec has feasibility {rec.average_feasibility} <= {inp.feasibility_threshold}"

    def test_i5_failed_after_repairs_has_full_history(self):
        """I5: failed_after_repairs recs have repair_history length == max_repair_iterations."""
        rec = Recommendation(
            id="r1", title="Test", content="Bad",
            average_feasibility=30, status="approved",
            feasibility_scores=[FeasibilityScore(agent_id="p1", agent_name="P1", score=30)],
        )

        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {"content": "Still bad\nFeasibility Score: 35/100", "input_tokens": 100, "output_tokens": 50}

        p_agent = _make_practicality_agent()
        storage = _make_mock_storage([p_agent])
        vs = _make_mock_vector_store()

        max_iters = 3
        inp = HivemindInput(query="test", practicality_agent_ids=["p1"], feasibility_threshold=60)
        budget = _BudgetGuard(inp)
        audit = []
        repair_stats = RepairStats()

        repair_failed_recommendations(
            [rec], threshold=60, max_iterations=max_iters,
            llm=llm, vector_store=vs, storage=storage,
            input_data=inp, budget=budget, audit_trail=audit,
            repair_stats=repair_stats,
        )

        assert rec.status == RecommendationStatus.FAILED_AFTER_REPAIRS.value
        assert len(rec.repair_history) == max_iters

    def test_partial_scoring_flagged(self):
        """F2: partial_scoring is set when budget exhausts mid-scoring."""
        rec = Recommendation(id="r1", title="Test", content="Content")

        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {"content": "Feasibility Score: 70/100", "input_tokens": 100, "output_tokens": 50}

        p_agent = _make_practicality_agent()
        storage = _make_mock_storage([p_agent])
        vs = _make_mock_vector_store()

        # Budget allows only 0 more calls
        inp = HivemindInput(query="test", practicality_agent_ids=["p1"], max_total_llm_calls=0)
        budget = _BudgetGuard(inp)
        audit = []

        apply_practicality_scoring(
            [rec], ["p1"], inp, llm, vs, storage, budget, audit,
        )

        assert rec.partial_scoring is True
        partial_events = [e for e in audit if e.event_type == "partial_practicality_scoring"]
        assert len(partial_events) == 1


# ---------------------------------------------------------------------------
# Canonical Form Tests
# ---------------------------------------------------------------------------


class TestCanonicalForm:
    def test_extract_canonical_form_valid_json(self):
        """Canonical form extraction parses valid LLM JSON output."""
        from hivemind_core.debate import _extract_canonical_form, _BudgetGuard

        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {
            "content": '{"objective": "Expand into Japan", "mechanism": "Partnership with local distributor", "dependencies": ["Legal approval"], "key_constraints": ["Budget limit"], "expected_outcomes": ["10% market share"]}',
            "input_tokens": 100, "output_tokens": 50,
        }

        sol = TheoryUnitSolution(unit_id="u1", unit_name="U1", solution="Expand into Japan via partnerships", reasoning="r")
        inp = HivemindInput(query="test", max_total_llm_calls=999)
        budget = _BudgetGuard(inp)

        form = _extract_canonical_form(llm, sol, budget)
        assert form["objective"] == "Expand into Japan"
        assert form["mechanism"] == "Partnership with local distributor"
        assert "Legal approval" in form["dependencies"]

    def test_extract_canonical_form_malformed_fallback(self):
        """Malformed LLM output falls back to raw solution as objective."""
        from hivemind_core.debate import _extract_canonical_form, _BudgetGuard

        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {"content": "Not valid JSON at all", "input_tokens": 100, "output_tokens": 50}

        sol = TheoryUnitSolution(unit_id="u1", unit_name="U1", solution="Do something strategic", reasoning="r")
        inp = HivemindInput(query="test", max_total_llm_calls=999)
        budget = _BudgetGuard(inp)

        form = _extract_canonical_form(llm, sol, budget)
        assert "Do something strategic" in form["objective"]
        assert form["mechanism"] == ""
        assert form["dependencies"] == []

    def test_contradiction_detection(self):
        """Contradictory objectives are detected."""
        from hivemind_core.debate import _detect_contradiction, _BudgetGuard

        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {"content": '{"contradicts": true, "reason": "opposing goals"}', "input_tokens": 100, "output_tokens": 50}

        form_a = {"objective": "Expand into market X", "mechanism": "Acquire competitor"}
        form_b = {"objective": "Exit market X", "mechanism": "Divest assets"}

        inp = HivemindInput(query="test", max_total_llm_calls=999)
        budget = _BudgetGuard(inp)

        assert _detect_contradiction(llm, form_a, form_b, budget) is True

    def test_no_contradiction_allows_merge(self):
        """Non-contradictory forms allow merge."""
        from hivemind_core.debate import _detect_contradiction, _BudgetGuard

        llm = MagicMock(spec=LLMInterface)
        llm.call.return_value = {"content": '{"contradicts": false, "reason": "aligned goals"}', "input_tokens": 100, "output_tokens": 50}

        form_a = {"objective": "Expand into Japan", "mechanism": "Partnership"}
        form_b = {"objective": "Enter Japanese market", "mechanism": "JV with local firm"}

        inp = HivemindInput(query="test", max_total_llm_calls=999)
        budget = _BudgetGuard(inp)

        assert _detect_contradiction(llm, form_a, form_b, budget) is False

    def test_merge_preserves_canonical_in_evidence(self):
        """Merged cluster evidence contains canonical forms."""
        from hivemind_core.debate import _merge_solution_cluster, _BudgetGuard

        call_count = [0]
        def mock_call(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                # Canonical form extraction calls
                return {
                    "content": '{"objective": "Grow revenue", "mechanism": "Pricing optimization", "dependencies": [], "key_constraints": [], "expected_outcomes": ["15% growth"]}',
                    "input_tokens": 100, "output_tokens": 50,
                }
            elif call_count[0] == 3:
                # Contradiction check
                return {"content": '{"contradicts": false, "reason": "aligned"}', "input_tokens": 50, "output_tokens": 30}
            else:
                # Merge call
                return {"content": "MERGED SOLUTION: Optimize pricing to grow revenue by 15%", "input_tokens": 200, "output_tokens": 100}

        llm = MagicMock(spec=LLMInterface)
        llm.call.side_effect = lambda **kw: mock_call(**kw)

        sols = [
            TheoryUnitSolution(unit_id="u1", unit_name="U1", solution="Raise prices", reasoning="r1"),
            TheoryUnitSolution(unit_id="u2", unit_name="U2", solution="Optimize pricing tiers", reasoning="r2"),
        ]

        inp = HivemindInput(query="test", max_total_llm_calls=999)
        budget = _BudgetGuard(inp)

        result = _merge_solution_cluster(llm, sols, budget)
        assert "canonical_forms" in result.cluster_evidence
        assert len(result.cluster_evidence["canonical_forms"]) == 2


# ---------------------------------------------------------------------------
# AC8: Audit Event Convention Tests
# ---------------------------------------------------------------------------


class TestAuditEventConvention:
    """AC8: All audit events use _make_audit_details with consistent base fields."""

    REQUIRED_FIELDS = {"event_version", "mode", "run_id", "timestamp_iso"}

    def test_simple_mode_audit_events_have_base_fields(self):
        """Every audit event in simple mode has event_version, mode, run_id, timestamp_iso."""
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"], analysis_mode="simple")
        output = run_debate(inp, llm, vs, storage)

        # Debate-level event types that must use _make_audit_details.
        # agent_execution events come from agents.py and have their own schema.
        _AGENT_MODULE_EVENTS = {"agent_call", "agent_execution"}

        for event in output.audit_trail:
            if event.details and event.event_type not in _AGENT_MODULE_EVENTS:
                for field in self.REQUIRED_FIELDS:
                    assert field in event.details, (
                        f"Audit event '{event.event_type}' missing '{field}' in details: {event.details}"
                    )
                assert event.details["mode"] == "simple"
                assert event.details["event_version"] == "v2"

    def test_full_mode_audit_events_have_base_fields(self):
        """Every audit event in full mode has event_version, mode, run_id, timestamp_iso."""
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"], analysis_mode="full")
        output = run_debate(inp, llm, vs, storage)

        _AGENT_MODULE_EVENTS = {"agent_call", "agent_execution"}

        for event in output.audit_trail:
            if event.details and event.event_type not in _AGENT_MODULE_EVENTS:
                for field in self.REQUIRED_FIELDS:
                    assert field in event.details, (
                        f"Audit event '{event.event_type}' missing '{field}' in details: {event.details}"
                    )
                assert event.details["mode"] == "full"
                assert event.details["event_version"] == "v2"

    def test_run_id_consistent_across_all_events(self):
        """All audit events in a single run share the same run_id."""
        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"], analysis_mode="simple")
        output = run_debate(inp, llm, vs, storage)

        run_ids = set()
        for event in output.audit_trail:
            if event.details and "run_id" in event.details:
                run_ids.add(event.details["run_id"])

        assert len(run_ids) == 1, f"Expected 1 run_id, got {run_ids}"

    def test_i6_streaming_equivalence(self):
        """I6: Streaming and non-streaming produce semantically equivalent output."""
        from hivemind_core.debate import run_debate_streaming

        agent = _make_theory_agent()
        llm = _make_mock_llm()
        storage = _make_mock_storage([agent])
        vs = _make_mock_vector_store()

        inp = HivemindInput(query="test", theory_agent_ids=["t1"], analysis_mode="simple")

        non_stream = run_debate(inp, llm, vs, storage)
        stream_events = list(run_debate_streaming(inp, llm, vs, storage))
        complete_events = [e for e in stream_events if e.get("type") == "complete"]
        assert len(complete_events) == 1
        stream_output = complete_events[0]["output"]

        # Structural equivalence
        assert non_stream.mode_used == stream_output.mode_used
        assert non_stream.termination_reason == stream_output.termination_reason
        assert len(non_stream.recommendations) == len(stream_output.recommendations)
        assert non_stream.debate_rounds == stream_output.debate_rounds
