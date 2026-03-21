"""Tests for debate.py helper / parsing functions."""

import pytest

from hivemind_core.debate import (
    _aggregated_to_recommendations,
    _BudgetGuard,
    _create_dynamic_units,
    _parse_critique_response,
    _parse_feasibility_score,
    _parse_solution_reasoning,
    _StagnationDetector,
)
from hivemind_core.types import (
    AggregatedSolution,
    BudgetExhausted,
    HivemindInput,
)


def test_parse_solution_reasoning_with_labels():
    text = "SOLUTION: Do X\nREASONING: Because Y"
    sol, rea = _parse_solution_reasoning(text)
    assert "Do X" in sol
    assert "Because Y" in rea


def test_parse_solution_reasoning_no_labels():
    text = "Just a plain response"
    sol, rea = _parse_solution_reasoning(text)
    assert sol == text.strip()
    assert rea == text.strip()


def test_parse_critique_response_extracts_bullets():
    text = """STRENGTHS:
- Good market analysis
- Solid data

WEAKNESSES:
- Missing risk assessment

SUGGESTIONS:
- Add competitive analysis
"""
    strengths, weaknesses, suggestions = _parse_critique_response(text)
    assert len(strengths) == 2
    assert len(weaknesses) == 1
    assert len(suggestions) == 1
    assert "Good market analysis" in strengths[0]


def test_parse_critique_response_empty():
    strengths, weaknesses, suggestions = _parse_critique_response("No structured content")
    assert strengths == []
    assert weaknesses == []
    assert suggestions == []


def test_create_dynamic_units_basic():
    doc_tokens = {"d1": 1000, "d2": 2000, "d3": 1500}
    units = _create_dynamic_units(
        density_value=2500,
        all_document_ids=["d1", "d2", "d3"],
        document_tokens=doc_tokens,
    )
    assert len(units) >= 1
    # All documents should be assigned
    all_assigned = []
    for u in units:
        all_assigned.extend(u.assigned_document_ids)
    assert set(all_assigned) == {"d1", "d2", "d3"}


def test_create_dynamic_units_empty():
    units = _create_dynamic_units(density_value=1000, all_document_ids=[], document_tokens={})
    assert units == []


def test_create_dynamic_units_single_large_doc():
    doc_tokens = {"d1": 10000}
    units = _create_dynamic_units(
        density_value=5000,
        all_document_ids=["d1"],
        document_tokens=doc_tokens,
    )
    assert len(units) == 1
    assert units[0].assigned_document_ids == ["d1"]


def test_parse_feasibility_score_basic():
    response = """Feasibility Score: 75/100

RISKS:
- Market uncertainty
- Competitor response

CHALLENGES:
- Resource constraints

MITIGATIONS:
- Phased rollout
"""
    score, risks, challenges, mitigations, reasoning = _parse_feasibility_score(response)
    assert score == 75
    assert len(risks) == 2
    assert len(challenges) == 1
    assert len(mitigations) == 1


def test_parse_feasibility_score_no_score():
    response = "This is a general evaluation with no score marker."
    score, risks, challenges, mitigations, reasoning = _parse_feasibility_score(response)
    assert score == 50  # default


# ---------------------------------------------------------------------------
# Budget Guard Tests
# ---------------------------------------------------------------------------


def test_budget_guard_enforces_llm_call_limit():
    inp = HivemindInput(query="test", max_total_llm_calls=3, effort_level="medium")
    guard = _BudgetGuard(inp)

    guard.record_call({"input_tokens": 100, "output_tokens": 50})
    guard.record_call({"input_tokens": 100, "output_tokens": 50})
    guard.record_call({"input_tokens": 100, "output_tokens": 50})

    with pytest.raises(BudgetExhausted, match="LLM call limit"):
        guard.check()


def test_budget_guard_enforces_token_limit():
    inp = HivemindInput(query="test", max_total_tokens=500, max_total_llm_calls=999)
    guard = _BudgetGuard(inp)

    guard.record_call({"input_tokens": 200, "output_tokens": 200})
    guard.record_call({"input_tokens": 100, "output_tokens": 50})

    with pytest.raises(BudgetExhausted, match="Token limit"):
        guard.check()


def test_budget_guard_finalize():
    inp = HivemindInput(query="test", max_total_llm_calls=999)
    guard = _BudgetGuard(inp)
    guard.record_call({"input_tokens": 100, "output_tokens": 50})
    usage = guard.finalize()
    assert usage.llm_calls == 1
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.total_tokens == 150
    assert usage.wallclock_ms >= 0


def test_budget_guard_uses_effort_defaults():
    inp = HivemindInput(query="test", effort_level="low")
    guard = _BudgetGuard(inp)
    assert guard.max_llm_calls == 30

    inp2 = HivemindInput(query="test", effort_level="high")
    guard2 = _BudgetGuard(inp2)
    assert guard2.max_llm_calls == 160


def test_budget_guard_explicit_overrides_effort():
    inp = HivemindInput(query="test", effort_level="low", max_total_llm_calls=100)
    guard = _BudgetGuard(inp)
    assert guard.max_llm_calls == 100


# ---------------------------------------------------------------------------
# Stagnation Detector Tests
# ---------------------------------------------------------------------------


def test_stagnation_detector_detects_no_improvement():
    sd = _StagnationDetector(window=2, min_improvement=1)
    sd.record(5)
    sd.record(5)
    sd.record(5)
    assert sd.is_stagnant() is True


def test_stagnation_detector_not_stagnant_with_improvement():
    sd = _StagnationDetector(window=2, min_improvement=1)
    sd.record(5)
    sd.record(4)
    sd.record(3)
    assert sd.is_stagnant() is False


def test_stagnation_detector_too_few_records():
    sd = _StagnationDetector(window=2, min_improvement=1)
    sd.record(5)
    sd.record(5)
    assert sd.is_stagnant() is False  # Need 3 records for window=2


def test_stagnation_detector_min_improvement_threshold():
    sd = _StagnationDetector(window=2, min_improvement=2)
    sd.record(5)
    sd.record(4)
    sd.record(4)
    # improvement = 5 - 4 = 1, less than min_improvement=2
    assert sd.is_stagnant() is True


# ---------------------------------------------------------------------------
# Aggregated to Recommendations
# ---------------------------------------------------------------------------


def test_aggregated_to_recommendations():
    agg = [
        AggregatedSolution(
            id="agg-1",
            merged_solution="Solution A",
            contributing_units=["u1", "u2"],
            justifications=["reason1", "reason2"],
            confidence_score=0.8,
        ),
    ]
    recs = _aggregated_to_recommendations(agg)
    assert len(recs) == 1
    assert recs[0].id == "agg-1"
    assert "Solution A" in recs[0].content
    assert len(recs[0].contributing_agents) == 2
    assert recs[0].status == "approved"  # default
