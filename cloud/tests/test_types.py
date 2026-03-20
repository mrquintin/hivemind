"""Tests for hivemind_core.types dataclasses and enums."""

from hivemind_core.types import (
    AgentDefinition,
    AgentStatus,
    ContextItem,
    ContextType,
    DynamicTheoryUnit,
    HivemindInput,
    HivemindOutput,
    NetworkType,
    RagConfig,
    Recommendation,
    RetrievedChunk,
    SimulationFormula,
    StorageInterface,
    TheoryUnitSolution,
    VectorStoreInterface,
)


def test_context_type_enum():
    assert ContextType.TEXT == "text"
    assert ContextType.SENSOR == "sensor"
    assert ContextType.STRUCTURED == "structured"


def test_network_type_enum():
    assert NetworkType.THEORY == "theory"
    assert NetworkType.PRACTICALITY == "practicality"


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
