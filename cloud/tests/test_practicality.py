"""Tests for apply_practicality_scoring in debate.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from hivemind_core.debate import _BudgetGuard, apply_practicality_scoring
from hivemind_core.types import (
    AgentDefinition,
    AgentExecutionResult,
    AuditEvent,
    HivemindInput,
    LLMInterface,
    NetworkType,
    Recommendation,
    StorageInterface,
    VectorStoreInterface,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FEASIBILITY_RESPONSE = (
    "Feasibility Score: 85/100\n"
    "RISKS:\n"
    "- risk1\n"
    "CHALLENGES:\n"
    "- ch1\n"
    "MITIGATIONS:\n"
    "- mit1"
)


def _make_practicality_agent(agent_id: str, name: str) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        name=name,
        network_type=NetworkType.PRACTICALITY,
        scoring_criteria="cost, timeline, resources",
        score_interpretation="higher is better",
    )


def _make_execute_return(agent_id: str, agent_name: str):
    """Return a (AgentExecutionResult, AuditEvent) pair matching execute_agent's signature."""
    result = AgentExecutionResult(
        agent_id=agent_id,
        agent_name=agent_name,
        network_type="practicality",
        response=FEASIBILITY_RESPONSE,
        retrieved_chunk_ids=[],
        input_tokens=100,
        output_tokens=50,
    )
    audit = AuditEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="agent_execution",
        agent_id=agent_id,
        input_tokens=100,
        output_tokens=50,
    )
    return result, audit


def _build_fixtures(
    agent_ids=("p1",),
    agent_names=("PracticalityAgent1",),
    max_total_llm_calls=999,
    practicality_criticality=0.5,
):
    """Build the common set of mocks and objects used by most tests."""
    agents = {
        aid: _make_practicality_agent(aid, aname)
        for aid, aname in zip(agent_ids, agent_names)
    }

    storage = MagicMock(spec=StorageInterface)
    storage.get_agent.side_effect = lambda aid: agents.get(aid)

    vs = MagicMock(spec=VectorStoreInterface)
    vs.retrieve.return_value = []

    llm = MagicMock(spec=LLMInterface)

    input_data = HivemindInput(
        query="test",
        max_total_llm_calls=max_total_llm_calls,
        practicality_criticality=practicality_criticality,
    )
    budget = _BudgetGuard(input_data)
    audit_trail: list[AuditEvent] = []
    rec = Recommendation(id="r1", title="Test", content="Test content", average_feasibility=0)

    return storage, vs, llm, input_data, budget, audit_trail, rec, list(agent_ids)


# ---------------------------------------------------------------------------
# Test 1: Scoring populates feasibility_scores and average_feasibility
# ---------------------------------------------------------------------------


@patch("hivemind_core.debate.execute_agent")
def test_scoring_populates_feasibility_and_average(mock_execute):
    storage, vs, llm, input_data, budget, audit_trail, rec, agent_ids = _build_fixtures(
        agent_ids=("p1", "p2"),
        agent_names=("P1", "P2"),
    )

    mock_execute.side_effect = [
        _make_execute_return("p1", "P1"),
        _make_execute_return("p2", "P2"),
    ]

    apply_practicality_scoring(
        recommendations=[rec],
        practicality_agent_ids=agent_ids,
        input_data=input_data,
        llm=llm,
        vector_store=vs,
        storage=storage,
        budget=budget,
        audit_trail=audit_trail,
    )

    assert len(rec.feasibility_scores) == 2
    assert all(fs.score == 85 for fs in rec.feasibility_scores)
    assert rec.average_feasibility == 85.0
    assert rec.partial_scoring is False


# ---------------------------------------------------------------------------
# Test 2: Partial scoring on BudgetExhausted
# ---------------------------------------------------------------------------


@patch("hivemind_core.debate.execute_agent")
def test_partial_scoring_on_budget_exhausted(mock_execute):
    storage, vs, llm, input_data, budget, audit_trail, rec, _ = _build_fixtures(
        agent_ids=("p1", "p2"),
        agent_names=("P1", "P2"),
        max_total_llm_calls=1,
    )

    # First agent call succeeds and consumes the single allowed LLM call
    mock_execute.side_effect = [
        _make_execute_return("p1", "P1"),
    ]

    apply_practicality_scoring(
        recommendations=[rec],
        practicality_agent_ids=["p1", "p2"],
        input_data=input_data,
        llm=llm,
        vector_store=vs,
        storage=storage,
        budget=budget,
        audit_trail=audit_trail,
        mode="full",
        run_id="run-abc",
    )

    # The first agent scored, but the second hit budget exhaustion
    assert rec.partial_scoring is True
    assert len(rec.feasibility_scores) == 1
    assert rec.feasibility_scores[0].score == 85
    assert rec.average_feasibility == 85.0

    # Verify the partial_practicality_scoring audit event was emitted
    partial_events = [e for e in audit_trail if e.event_type == "partial_practicality_scoring"]
    assert len(partial_events) == 1
    assert partial_events[0].details["reason"] == "budget_exhausted"
    assert partial_events[0].details["rec_id"] == "r1"
    assert partial_events[0].details["agents_scored"] == 1
    assert partial_events[0].details["agents_total"] == 2


# ---------------------------------------------------------------------------
# Test 3: Empty practicality_agent_ids -> no-op
# ---------------------------------------------------------------------------


def test_empty_agent_ids_is_noop():
    storage, vs, llm, input_data, budget, audit_trail, rec, _ = _build_fixtures()

    original_feasibility = rec.average_feasibility
    original_scores = list(rec.feasibility_scores)

    apply_practicality_scoring(
        recommendations=[rec],
        practicality_agent_ids=[],
        input_data=input_data,
        llm=llm,
        vector_store=vs,
        storage=storage,
        budget=budget,
        audit_trail=audit_trail,
    )

    assert rec.feasibility_scores == original_scores
    assert rec.average_feasibility == original_feasibility
    assert len(audit_trail) == 0


# ---------------------------------------------------------------------------
# Test 4: practicality_criticality value appears in the prompt
# ---------------------------------------------------------------------------


@patch("hivemind_core.debate.execute_agent")
def test_criticality_in_prompt(mock_execute):
    storage, vs, llm, input_data, budget, audit_trail, rec, agent_ids = _build_fixtures(
        practicality_criticality=0.7,
    )

    mock_execute.side_effect = [_make_execute_return("p1", "PracticalityAgent1")]

    apply_practicality_scoring(
        recommendations=[rec],
        practicality_agent_ids=agent_ids,
        input_data=input_data,
        llm=llm,
        vector_store=vs,
        storage=storage,
        budget=budget,
        audit_trail=audit_trail,
    )

    # execute_agent is called with a query kwarg containing the criticality percentage
    call_kwargs = mock_execute.call_args
    query_arg = call_kwargs.kwargs.get("query") or call_kwargs[1].get("query") or call_kwargs[0][1]
    assert "70%" in query_arg, f"Expected '70%' in query, got: {query_arg}"


# ---------------------------------------------------------------------------
# Test 5: Audit event for partial_practicality_scoring has mode and run_id
# ---------------------------------------------------------------------------


@patch("hivemind_core.debate.execute_agent")
def test_partial_audit_has_mode_and_run_id(mock_execute):
    storage, vs, llm, input_data, budget, audit_trail, rec, _ = _build_fixtures(
        agent_ids=("p1", "p2"),
        agent_names=("P1", "P2"),
        max_total_llm_calls=1,
    )

    mock_execute.side_effect = [_make_execute_return("p1", "P1")]

    apply_practicality_scoring(
        recommendations=[rec],
        practicality_agent_ids=["p1", "p2"],
        input_data=input_data,
        llm=llm,
        vector_store=vs,
        storage=storage,
        budget=budget,
        audit_trail=audit_trail,
        mode="full",
        run_id="run-xyz",
    )

    partial_events = [e for e in audit_trail if e.event_type == "partial_practicality_scoring"]
    assert len(partial_events) == 1

    details = partial_events[0].details
    # _make_audit_details convention: mode, run_id, event_version present
    assert details["mode"] == "full"
    assert details["run_id"] == "run-xyz"
    assert "event_version" in details
