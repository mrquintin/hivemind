"""Tests for hivemind_core.types dataclasses and enums."""

from hivemind_core.types import (
    EFFORT_DEFAULTS,
    AgentDefinition,
    AgentStatus,
    AnalysisMode,
    BudgetExhausted,
    BudgetUsage,
    ContextType,
    DynamicTheoryUnit,
    EffortLevel,
    HivemindInput,
    HivemindOutput,
    NetworkType,
    Recommendation,
    RecommendationStatus,
    RepairStats,
    RetrievedChunk,
    SimulationFormula,
    StorageInterface,
    TerminationReason,
    VectorStoreInterface,
)


def test_context_type_enum():
    assert ContextType.TEXT == "text"
    assert ContextType.SENSOR == "sensor"
    assert ContextType.STRUCTURED == "structured"


def test_network_type_enum():
    assert NetworkType.THEORY == "theory"
    assert NetworkType.PRACTICALITY == "practicality"


def test_analysis_mode_enum():
    assert AnalysisMode.SIMPLE == "simple"
    assert AnalysisMode.FULL == "full"


def test_effort_level_enum():
    assert EffortLevel.LOW == "low"
    assert EffortLevel.MEDIUM == "medium"
    assert EffortLevel.HIGH == "high"


def test_termination_reason_enum():
    assert TerminationReason.SIMPLE_COMPLETED == "simple_completed"
    assert TerminationReason.SUFFICIENCY_REACHED == "sufficiency_reached"
    assert TerminationReason.BUDGET_EXHAUSTED == "budget_exhausted"
    assert TerminationReason.STAGNATION_EARLY_STOP == "stagnation_early_stop"
    assert TerminationReason.COMPLETED_WITH_REPAIRS == "completed_with_repairs"
    assert TerminationReason.GLOBAL_RESTART_EXHAUSTED == "global_restart_exhausted"
    assert TerminationReason.VALIDATION_ERROR == "validation_error"


def test_recommendation_status_enum():
    assert RecommendationStatus.APPROVED == "approved"
    assert RecommendationStatus.VETOED == "vetoed"
    assert RecommendationStatus.FAILED_AFTER_REPAIRS == "failed_after_repairs"


def test_effort_defaults():
    assert EFFORT_DEFAULTS["low"]["max_rounds"] == 2
    assert EFFORT_DEFAULTS["medium"]["max_rounds"] == 4
    assert EFFORT_DEFAULTS["high"]["max_rounds"] == 6
    assert EFFORT_DEFAULTS["low"]["max_total_llm_calls"] == 30
    assert EFFORT_DEFAULTS["high"]["max_total_llm_calls"] == 160


def test_agent_definition_defaults():
    agent = AgentDefinition(id="a1", name="Test", network_type=NetworkType.THEORY)
    assert agent.knowledge_base_ids == []
    assert agent.document_ids == []
    assert agent.simulation_formula_ids == []
    assert agent.status == AgentStatus.DRAFT
    assert agent.version == 1


def test_hivemind_input_defaults():
    inp = HivemindInput(query="test query")
    assert inp.sufficiency_value == 1
    assert inp.feasibility_threshold == 80
    assert inp.theory_network_density is None
    assert inp.max_veto_restarts == 3
    assert inp.similarity_threshold == 0.65
    assert inp.revision_strength == 0.5
    assert inp.practicality_criticality == 0.5
    assert inp.analysis_mode == "simple"
    assert inp.effort_level == "medium"
    assert inp.max_total_llm_calls is None
    assert inp.max_total_tokens is None
    assert inp.max_wallclock_ms is None
    assert inp.max_repair_iterations == 2
    assert inp.stagnation_window_rounds == 2
    assert inp.min_aggregation_improvement == 1


def test_hivemind_input_effective_max_rounds():
    low = HivemindInput(query="q", effort_level="low")
    med = HivemindInput(query="q", effort_level="medium")
    high = HivemindInput(query="q", effort_level="high")
    assert low.get_effective_max_rounds() == 2
    assert med.get_effective_max_rounds() == 4
    assert high.get_effective_max_rounds() == 6


def test_hivemind_input_effective_max_llm_calls():
    # Default from effort level
    inp = HivemindInput(query="q", effort_level="low")
    assert inp.get_effective_max_llm_calls() == 30

    # Explicit override
    inp2 = HivemindInput(query="q", effort_level="low", max_total_llm_calls=50)
    assert inp2.get_effective_max_llm_calls() == 50


def test_hivemind_output_new_fields():
    out = HivemindOutput(id="test-123")
    assert out.termination_reason == ""
    assert out.mode_used == "simple"
    assert out.budget_usage.llm_calls == 0
    assert out.repair_stats.recommendations_repaired == 0


def test_recommendation_new_fields():
    rec = Recommendation(id="r1", title="Test", content="content")
    assert rec.status == "approved"
    assert rec.repair_history == []


def test_budget_usage_dataclass():
    bu = BudgetUsage(llm_calls=5, input_tokens=100, output_tokens=50, total_tokens=150, wallclock_ms=1000)
    assert bu.llm_calls == 5
    assert bu.total_tokens == 150


def test_repair_stats_dataclass():
    rs = RepairStats(recommendations_repaired=3, recommendations_recovered=2,
                     recommendations_failed_after_repairs=1, total_repair_iterations=5)
    assert rs.recommendations_repaired == 3
    assert rs.recommendations_recovered == 2


def test_budget_exhausted_exception():
    try:
        raise BudgetExhausted("test limit")
    except BudgetExhausted as e:
        assert "test limit" in str(e)


def test_dynamic_theory_unit():
    unit = DynamicTheoryUnit(
        id="u1", name="Unit 1",
        assigned_document_ids=["d1", "d2"],
        total_tokens=5000,
    )
    assert len(unit.assigned_document_ids) == 2
    assert unit.total_tokens == 5000


def test_storage_interface_raises():
    si = StorageInterface()
    try:
        si.get_agent("x")
        assert False, "Should raise"
    except NotImplementedError:
        pass


def test_vector_store_interface_retrieve_signature():
    """VectorStoreInterface.retrieve accepts document_ids kwarg."""
    vi = VectorStoreInterface()
    try:
        vi.retrieve("q", ["kb1"], document_ids=["d1"])
    except NotImplementedError:
        pass


def test_backward_compat_aliases():
    from hivemind_core.types import AgentConfig, SimulationConfig, TextChunk
    assert AgentConfig is AgentDefinition
    assert SimulationConfig is SimulationFormula
    assert TextChunk is RetrievedChunk


def test_backward_compat_hivemind_input():
    """Old-style HivemindInput without new fields still works."""
    inp = HivemindInput(
        query="Should we expand?",
        theory_agent_ids=["a1"],
        practicality_agent_ids=["p1"],
        sufficiency_value=2,
        feasibility_threshold=60,
        max_veto_restarts=3,
    )
    # New fields should have safe defaults
    assert inp.analysis_mode == "simple"
    assert inp.effort_level == "medium"
    assert inp.max_total_llm_calls is None
    assert inp.get_effective_max_llm_calls() == 80  # medium default


def test_aggregated_solution_cluster_evidence():
    """AggregatedSolution now has cluster_evidence field."""
    from hivemind_core.types import AggregatedSolution
    agg = AggregatedSolution(id="a1", merged_solution="test")
    assert agg.cluster_evidence == {}
    agg2 = AggregatedSolution(id="a2", merged_solution="test",
                               cluster_evidence={"cluster_id": "c1"})
    assert agg2.cluster_evidence["cluster_id"] == "c1"
