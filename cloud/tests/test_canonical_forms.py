"""Tests for the canonical form pipeline in debate.py.

Covers:
- _extract_canonical_form: valid JSON, malformed JSON, budget exhaustion
- _detect_contradiction: contradicting pair, non-contradicting pair, budget exhaustion
- _merge_canonical_forms: multiple forms with dedup, empty list
- cluster_solutions_monitor_v2: end-to-end with 2 similar / single solution
"""

import json
from unittest.mock import MagicMock, patch

from hivemind_core.debate import (
    _BudgetGuard,
    _detect_contradiction,
    _extract_canonical_form,
    _merge_canonical_forms,
    cluster_solutions_monitor_v2,
)
from hivemind_core.types import (
    HivemindInput,
    LLMInterface,
    TheoryUnitSolution,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_budget(max_calls: int = 999) -> _BudgetGuard:
    """Create a BudgetGuard with generous limits."""
    return _BudgetGuard(HivemindInput(query="test", max_total_llm_calls=max_calls))


def _make_solution(unit_id: str = "u1", solution: str = "Do X", reasoning: str = "Because Y") -> TheoryUnitSolution:
    return TheoryUnitSolution(
        unit_id=unit_id,
        unit_name=f"Unit {unit_id}",
        solution=solution,
        reasoning=reasoning,
        knowledge_base_ids=[],
        retrieved_chunk_ids=[],
    )


def _make_llm(**overrides) -> MagicMock:
    llm = MagicMock(spec=LLMInterface)
    content = overrides.pop("content", "")
    llm.call.return_value = {
        "content": content,
        "input_tokens": 10,
        "output_tokens": 10,
        **overrides,
    }
    return llm


# ---------------------------------------------------------------------------
# _extract_canonical_form
# ---------------------------------------------------------------------------

class TestExtractCanonicalForm:
    """Tests for _extract_canonical_form."""

    def test_valid_json_response(self):
        """LLM returns well-formed JSON -> structured dict with all fields."""
        canonical = {
            "objective": "Increase market share",
            "mechanism": "Aggressive pricing strategy",
            "dependencies": ["supplier contracts", "distribution network"],
            "key_constraints": ["regulatory limits"],
            "expected_outcomes": ["10% market share gain", "brand recognition"],
        }
        llm = _make_llm(content=json.dumps(canonical))
        budget = _make_budget()
        sol = _make_solution(solution="We should increase market share via pricing")

        result = _extract_canonical_form(llm, sol, budget)

        assert result["objective"] == "Increase market share"
        assert result["mechanism"] == "Aggressive pricing strategy"
        assert result["dependencies"] == ["supplier contracts", "distribution network"]
        assert result["key_constraints"] == ["regulatory limits"]
        assert result["expected_outcomes"] == ["10% market share gain", "brand recognition"]
        llm.call.assert_called_once()

    def test_malformed_json_falls_back(self):
        """LLM returns non-JSON garbage -> fallback with raw solution text."""
        llm = _make_llm(content="This is not JSON at all, sorry!")
        budget = _make_budget()
        sol = _make_solution(solution="Expand into new markets")

        result = _extract_canonical_form(llm, sol, budget)

        assert result["objective"] == "Expand into new markets"
        assert result["mechanism"] == ""
        assert result["dependencies"] == []
        assert result["key_constraints"] == []
        assert result["expected_outcomes"] == []

    def test_budget_exhausted_returns_fallback(self):
        """Budget already exhausted -> returns fallback dict without calling LLM."""
        llm = _make_llm()
        budget = _make_budget(max_calls=0)  # Already at limit
        sol = _make_solution(solution="Some strategic plan")

        result = _extract_canonical_form(llm, sol, budget)

        assert result["objective"] == "Some strategic plan"
        assert result["mechanism"] == ""
        assert result["dependencies"] == []
        llm.call.assert_not_called()

    def test_json_embedded_in_text(self):
        """LLM returns JSON surrounded by explanation text -> still parses."""
        canonical = {
            "objective": "Reduce costs",
            "mechanism": "Automation",
            "dependencies": ["technology"],
            "key_constraints": ["budget"],
            "expected_outcomes": ["30% cost reduction"],
        }
        content = f"Here is the analysis:\n{json.dumps(canonical)}\nHope this helps!"
        llm = _make_llm(content=content)
        budget = _make_budget()
        sol = _make_solution()

        result = _extract_canonical_form(llm, sol, budget)

        assert result["objective"] == "Reduce costs"
        assert result["mechanism"] == "Automation"

    def test_truncates_long_fields(self):
        """Long objective/mechanism fields get truncated to 500 chars."""
        canonical = {
            "objective": "A" * 1000,
            "mechanism": "B" * 1000,
            "dependencies": ["C" * 500],
            "key_constraints": [],
            "expected_outcomes": [],
        }
        llm = _make_llm(content=json.dumps(canonical))
        budget = _make_budget()
        sol = _make_solution()

        result = _extract_canonical_form(llm, sol, budget)

        assert len(result["objective"]) == 500
        assert len(result["mechanism"]) == 500
        # Dependencies truncated to 200 chars each
        assert len(result["dependencies"][0]) == 200

    def test_records_budget_usage(self):
        """Successful call records budget usage."""
        canonical = {"objective": "test", "mechanism": "", "dependencies": [], "key_constraints": [], "expected_outcomes": []}
        llm = _make_llm(content=json.dumps(canonical))
        budget = _make_budget()
        sol = _make_solution()

        _extract_canonical_form(llm, sol, budget)

        assert budget.usage.llm_calls == 1
        assert budget.usage.total_tokens == 20  # 10 in + 10 out


# ---------------------------------------------------------------------------
# _detect_contradiction
# ---------------------------------------------------------------------------

class TestDetectContradiction:
    """Tests for _detect_contradiction."""

    def test_contradicting_pair(self):
        """LLM says approaches contradict -> returns True."""
        llm = _make_llm(content=json.dumps({"contradicts": True, "reason": "opposing goals"}))
        budget = _make_budget()
        form_a = {"objective": "Increase prices", "mechanism": "Premium positioning"}
        form_b = {"objective": "Decrease prices", "mechanism": "Volume strategy"}

        result = _detect_contradiction(llm, form_a, form_b, budget)

        assert result is True
        llm.call.assert_called_once()

    def test_non_contradicting_pair(self):
        """LLM says approaches are compatible -> returns False."""
        llm = _make_llm(content=json.dumps({"contradicts": False, "reason": "complementary strategies"}))
        budget = _make_budget()
        form_a = {"objective": "Increase revenue", "mechanism": "Expand sales team"}
        form_b = {"objective": "Increase revenue", "mechanism": "Improve marketing"}

        result = _detect_contradiction(llm, form_a, form_b, budget)

        assert result is False

    def test_budget_exhausted_returns_false(self):
        """Budget exhausted -> conservative False (allow merge)."""
        llm = _make_llm()
        budget = _make_budget(max_calls=0)
        form_a = {"objective": "Go north", "mechanism": "Walk"}
        form_b = {"objective": "Go south", "mechanism": "Drive"}

        result = _detect_contradiction(llm, form_a, form_b, budget)

        assert result is False
        llm.call.assert_not_called()

    def test_identical_objectives_short_circuits(self):
        """Identical objective + mechanism -> returns False without LLM call."""
        llm = _make_llm()
        budget = _make_budget()
        form_a = {"objective": "Same goal", "mechanism": "Same method"}
        form_b = {"objective": "Same goal", "mechanism": "Same method"}

        result = _detect_contradiction(llm, form_a, form_b, budget)

        assert result is False
        llm.call.assert_not_called()

    def test_empty_objective_short_circuits(self):
        """Empty objective in either form -> returns False without LLM call."""
        llm = _make_llm()
        budget = _make_budget()
        form_a = {"objective": "", "mechanism": "Some method"}
        form_b = {"objective": "Some goal", "mechanism": "Another method"}

        result = _detect_contradiction(llm, form_a, form_b, budget)

        assert result is False
        llm.call.assert_not_called()

    def test_malformed_llm_response_returns_false(self):
        """LLM returns unparseable response -> conservative False."""
        llm = _make_llm(content="I cannot determine this.")
        budget = _make_budget()
        form_a = {"objective": "Goal A", "mechanism": "Method A"}
        form_b = {"objective": "Goal B", "mechanism": "Method B"}

        result = _detect_contradiction(llm, form_a, form_b, budget)

        assert result is False

    def test_records_budget_usage(self):
        """Successful contradiction check records budget usage."""
        llm = _make_llm(content=json.dumps({"contradicts": False, "reason": "ok"}))
        budget = _make_budget()
        form_a = {"objective": "Goal A", "mechanism": "Method A"}
        form_b = {"objective": "Goal B", "mechanism": "Method B"}

        _detect_contradiction(llm, form_a, form_b, budget)

        assert budget.usage.llm_calls == 1


# ---------------------------------------------------------------------------
# _merge_canonical_forms
# ---------------------------------------------------------------------------

class TestMergeCanonicalForms:
    """Tests for _merge_canonical_forms."""

    def test_merge_multiple_forms(self):
        """Multiple forms -> merges unique entries, deduplicates lists."""
        forms = [
            {
                "objective": "Grow revenue",
                "mechanism": "Sales expansion",
                "dependencies": ["team", "budget"],
                "key_constraints": ["regulation"],
                "expected_outcomes": ["10% growth"],
            },
            {
                "objective": "Grow revenue faster",
                "mechanism": "Marketing push",
                "dependencies": ["budget", "brand"],
                "key_constraints": ["regulation", "market size"],
                "expected_outcomes": ["10% growth", "brand awareness"],
            },
        ]

        result = _merge_canonical_forms(forms)

        # Objective/mechanism take the first form's values
        assert result["objective"] == "Grow revenue"
        assert result["mechanism"] == "Sales expansion"
        # Dependencies deduplicated: team, budget, brand (budget not repeated)
        assert result["dependencies"] == ["team", "budget", "brand"]
        # Constraints deduplicated
        assert result["key_constraints"] == ["regulation", "market size"]
        # Outcomes deduplicated
        assert result["expected_outcomes"] == ["10% growth", "brand awareness"]

    def test_empty_list(self):
        """Empty list -> returns empty structure."""
        result = _merge_canonical_forms([])

        assert result["objective"] == ""
        assert result["mechanism"] == ""
        assert result["dependencies"] == []
        assert result["key_constraints"] == []
        assert result["expected_outcomes"] == []

    def test_single_form(self):
        """Single form -> returns it unchanged."""
        form = {
            "objective": "Launch product",
            "mechanism": "Agile development",
            "dependencies": ["engineers"],
            "key_constraints": ["deadline"],
            "expected_outcomes": ["product launch"],
        }

        result = _merge_canonical_forms([form])

        assert result["objective"] == "Launch product"
        assert result["mechanism"] == "Agile development"
        assert result["dependencies"] == ["engineers"]
        assert result["key_constraints"] == ["deadline"]
        assert result["expected_outcomes"] == ["product launch"]

    def test_skips_empty_strings_in_lists(self):
        """Empty strings in dependencies/constraints/outcomes are skipped."""
        forms = [
            {
                "objective": "Goal",
                "mechanism": "Method",
                "dependencies": ["dep1", "", "dep2"],
                "key_constraints": [""],
                "expected_outcomes": ["outcome1"],
            },
        ]

        result = _merge_canonical_forms(forms)

        assert "" not in result["dependencies"]
        assert result["dependencies"] == ["dep1", "dep2"]
        assert result["key_constraints"] == []

    def test_forms_with_missing_keys(self):
        """Forms with missing keys -> uses defaults, no crash."""
        forms = [
            {"objective": "Goal A"},
            {"mechanism": "Method B", "dependencies": ["dep"]},
        ]

        result = _merge_canonical_forms(forms)

        assert result["objective"] == "Goal A"
        assert result["mechanism"] == "Method B"
        assert result["dependencies"] == ["dep"]

    def test_three_forms_deduplication(self):
        """Three forms with overlapping entries -> all unique preserved in order."""
        forms = [
            {"objective": "A", "mechanism": "M1", "dependencies": ["x", "y"], "key_constraints": [], "expected_outcomes": ["o1"]},
            {"objective": "B", "mechanism": "M2", "dependencies": ["y", "z"], "key_constraints": ["c1"], "expected_outcomes": ["o1", "o2"]},
            {"objective": "C", "mechanism": "M3", "dependencies": ["z", "w"], "key_constraints": ["c1", "c2"], "expected_outcomes": ["o3"]},
        ]

        result = _merge_canonical_forms(forms)

        assert result["objective"] == "A"  # First non-empty
        assert result["mechanism"] == "M1"  # First non-empty
        assert result["dependencies"] == ["x", "y", "z", "w"]
        assert result["key_constraints"] == ["c1", "c2"]
        assert result["expected_outcomes"] == ["o1", "o2", "o3"]


# ---------------------------------------------------------------------------
# cluster_solutions_monitor_v2 (end-to-end)
# ---------------------------------------------------------------------------

class TestClusterSolutionsMonitorV2:
    """End-to-end tests for cluster_solutions_monitor_v2."""

    @patch("hivemind_core.debate._compute_embedding_similarity")
    def test_two_similar_solutions_single_cluster(self, mock_embedding):
        """Two solutions with high embedding similarity -> clustered together."""
        # High similarity => skip LLM adjudication, go straight to merge
        mock_embedding.return_value = 0.95

        canonical = json.dumps({
            "objective": "Improve efficiency",
            "mechanism": "Process optimization",
            "dependencies": [],
            "key_constraints": [],
            "expected_outcomes": ["Better throughput"],
        })
        merged_text = "MERGED SOLUTION: Unified efficiency improvement plan"

        llm = MagicMock(spec=LLMInterface)
        # Calls: 2x _extract_canonical_form + 1x _detect_contradiction + 1x merge prompt
        # _detect_contradiction may short-circuit if objectives are identical
        llm.call.return_value = {
            "content": canonical,
            "input_tokens": 10,
            "output_tokens": 10,
        }
        # Override for the merge call (last call): return merged text
        def side_effect(**kwargs):
            prompt = kwargs.get("user_prompt", "")
            if "Multiple analysts" in prompt:
                return {"content": merged_text, "input_tokens": 10, "output_tokens": 10}
            if "contradicts" in prompt.lower() or "contradict" in prompt.lower():
                return {"content": json.dumps({"contradicts": False, "reason": "compatible"}), "input_tokens": 10, "output_tokens": 10}
            return {"content": canonical, "input_tokens": 10, "output_tokens": 10}

        llm.call.side_effect = side_effect

        sol1 = _make_solution(unit_id="u1", solution="Optimize processes for efficiency")
        sol2 = _make_solution(unit_id="u2", solution="Streamline workflows for efficiency")
        budget = _make_budget()

        aggregated, audit_events = cluster_solutions_monitor_v2(
            llm, [sol1, sol2], budget, threshold_high=0.80,
        )

        # Two similar solutions -> 1 cluster
        assert len(aggregated) == 1
        agg = aggregated[0]
        assert "u1" in agg.contributing_units
        assert "u2" in agg.contributing_units
        # Audit events should include monitor_v2_clustering
        event_types = [e.event_type for e in audit_events]
        assert "monitor_v2_clustering" in event_types

    @patch("hivemind_core.debate._compute_embedding_similarity")
    def test_single_solution_returns_one_cluster(self, mock_embedding):
        """Single solution -> returns exactly 1 cluster, no LLM calls needed."""
        llm = MagicMock(spec=LLMInterface)
        sol = _make_solution(unit_id="u1", solution="Standalone strategy")
        budget = _make_budget()

        aggregated, audit_events = cluster_solutions_monitor_v2(
            llm, [sol], budget,
        )

        assert len(aggregated) == 1
        agg = aggregated[0]
        assert agg.merged_solution == "Standalone strategy"
        assert agg.contributing_units == ["u1"]
        # No LLM calls should be made for a single solution (no pairs)
        llm.call.assert_not_called()
        # Embedding similarity is never called (no pairs)
        mock_embedding.assert_not_called()

    @patch("hivemind_core.debate._compute_embedding_similarity")
    def test_two_dissimilar_solutions_two_clusters(self, mock_embedding):
        """Two solutions with low embedding similarity -> two separate clusters."""
        mock_embedding.return_value = 0.2  # Very low similarity

        llm = MagicMock(spec=LLMInterface)
        sol1 = _make_solution(unit_id="u1", solution="Strategy Alpha")
        sol2 = _make_solution(unit_id="u2", solution="Strategy Beta completely different")
        budget = _make_budget()

        aggregated, audit_events = cluster_solutions_monitor_v2(
            llm, [sol1, sol2], budget, threshold_low=0.55,
        )

        # Low similarity -> 2 separate clusters
        assert len(aggregated) == 2
        # Each cluster has exactly one solution
        cluster_sizes = [len(a.contributing_units) for a in aggregated]
        assert sorted(cluster_sizes) == [1, 1]
        # No LLM call needed (embedding score below threshold_low)
        llm.call.assert_not_called()

    @patch("hivemind_core.debate._compute_embedding_similarity")
    def test_empty_solutions_returns_empty(self, mock_embedding):
        """Empty solution list -> returns empty results."""
        llm = MagicMock(spec=LLMInterface)
        budget = _make_budget()

        aggregated, audit_events = cluster_solutions_monitor_v2(
            llm, [], budget,
        )

        assert aggregated == []
        assert audit_events == []

    @patch("hivemind_core.debate._compute_embedding_similarity")
    def test_borderline_similarity_uses_llm_adjudication(self, mock_embedding):
        """Borderline embedding score triggers LLM adjudication."""
        # Score between threshold_low and threshold_high -> borderline
        mock_embedding.return_value = 0.65

        canonical = json.dumps({
            "objective": "Common goal",
            "mechanism": "Method",
            "dependencies": [],
            "key_constraints": [],
            "expected_outcomes": [],
        })

        def side_effect(**kwargs):
            prompt = kwargs.get("user_prompt", "")
            if "same core intent" in prompt:
                # LLM adjudication: say they are the same
                return {
                    "content": json.dumps({"same_intent": True, "confidence": 0.8, "rationale": "same approach"}),
                    "input_tokens": 10,
                    "output_tokens": 10,
                }
            if "Multiple analysts" in prompt:
                return {"content": "Merged recommendation", "input_tokens": 10, "output_tokens": 10}
            if "contradict" in prompt.lower():
                return {"content": json.dumps({"contradicts": False, "reason": "ok"}), "input_tokens": 10, "output_tokens": 10}
            return {"content": canonical, "input_tokens": 10, "output_tokens": 10}

        llm = MagicMock(spec=LLMInterface)
        llm.call.side_effect = side_effect

        sol1 = _make_solution(unit_id="u1", solution="Approach A for growth")
        sol2 = _make_solution(unit_id="u2", solution="Approach B for growth")
        budget = _make_budget()

        aggregated, audit_events = cluster_solutions_monitor_v2(
            llm, [sol1, sol2], budget,
            threshold_low=0.55,
            threshold_high=0.80,
        )

        # LLM adjudication said same_intent=True -> merged into 1 cluster
        assert len(aggregated) == 1
        assert "u1" in aggregated[0].contributing_units
        assert "u2" in aggregated[0].contributing_units
        # At least one LLM call should have been the adjudication
        assert llm.call.call_count >= 1

    @patch("hivemind_core.debate._compute_embedding_similarity")
    def test_cluster_evidence_populated(self, mock_embedding):
        """Cluster evidence dict is populated with expected metadata."""
        mock_embedding.return_value = 0.95
        llm = MagicMock(spec=LLMInterface)
        sol = _make_solution(unit_id="u1", solution="Only solution")
        budget = _make_budget()

        aggregated, _ = cluster_solutions_monitor_v2(llm, [sol], budget)

        agg = aggregated[0]
        assert "cluster_id" in agg.cluster_evidence
        assert "member_solution_ids" in agg.cluster_evidence
        assert agg.cluster_evidence["member_solution_ids"] == ["u1"]
