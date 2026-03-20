"""
Re-exports of the canonical interfaces defined in hivemind_core.types.

Import from here or from hivemind_core.types — they resolve to the same classes.
The InMemoryStorage helper is kept here for lightweight testing.
"""

from __future__ import annotations

from hivemind_core.types import (
    AgentDefinition,
    LLMInterface,
    RetrievedChunk,
    SimulationFormula,
    StorageInterface,
    VectorStoreInterface,
)

# Backward-compat aliases used by callers that import old names
AgentConfig = AgentDefinition
SimulationConfig = SimulationFormula
TextChunk = RetrievedChunk

__all__ = [
    "StorageInterface",
    "VectorStoreInterface",
    "LLMInterface",
    "InMemoryStorage",
    # aliases
    "AgentConfig",
    "SimulationConfig",
    "TextChunk",
]


class InMemoryStorage(StorageInterface):
    """In-memory storage for testing and edge deployments."""

    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}
        self._simulations: dict[str, SimulationFormula] = {}

    def add_agent(self, agent: AgentDefinition) -> None:
        self._agents[agent.id] = agent

    def add_simulation(self, sim: SimulationFormula) -> None:
        self._simulations[sim.id] = sim

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def list_agents(self, status=None) -> list[AgentDefinition]:
        agents = list(self._agents.values())
        if status is not None:
            agents = [a for a in agents if a.status == status]
        return agents

    def get_simulation(self, formula_id: str) -> SimulationFormula | None:
        return self._simulations.get(formula_id)

    def get_simulations(self, formula_ids: list[str]) -> list[SimulationFormula]:
        return [self._simulations[fid] for fid in formula_ids if fid in self._simulations]

    def get_documents_for_knowledge_bases(self, kb_ids: list[str]) -> list[dict]:
        return []
