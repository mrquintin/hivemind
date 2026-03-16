"""Tests for debate.py helper / parsing functions."""

from hivemind_core.debate import (
    _create_dynamic_units,
    _parse_critique_response,
    _parse_solution_reasoning,
)
from hivemind_core.types import DynamicTheoryUnit


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
