"""Main orchestrator for Hivemind core.

The HivemindEngine is the primary entry point for running analyses.
It coordinates agents, RAG, simulations, and the debate process.
"""
from __future__ import annotations

from hivemind_core.agents import execute_agent
from hivemind_core.debate import run_debate, run_debate_streaming
from hivemind_core.simulations import run_simulation
from hivemind_core.types import (
    AgentDefinition,
    AgentExecutionResult,
    AuditEvent,
    HivemindInput,
    HivemindOutput,
    LLMInterface,
    SimulationFormula,
    StorageInterface,
    VectorStoreInterface,
)


class HivemindEngine:
    """Main orchestrator for Hivemind strategic analysis.

    This is the platform-agnostic core that can be used from any transport
    layer (REST, WebSocket, MQTT, embedded, etc.).

    Example usage:
        >>> engine = HivemindEngine(llm=llm, vector_store=vs, storage=storage)
        >>> input_data = HivemindInput(query="Should we expand to Europe?", analysis_mode="simple")
        >>> output = engine.analyze(input_data)
    """

    def __init__(
        self,
        llm: LLMInterface,
        vector_store: VectorStoreInterface,
        storage: StorageInterface,
    ):
        self.llm = llm
        self.vector_store = vector_store
        self.storage = storage

    def analyze(
        self,
        input_data: HivemindInput,
        max_debate_rounds: int = 5,
    ) -> HivemindOutput:
        """Run a strategic analysis with the debate engine.

        Mode and effort are controlled via input_data.analysis_mode and
        input_data.effort_level. The max_debate_rounds parameter is kept
        for backward compatibility but is superseded by effort_level defaults.
        """
        return run_debate(
            input_data=input_data,
            llm=self.llm,
            vector_store=self.vector_store,
            storage=self.storage,
            max_rounds=max_debate_rounds,
        )

    def analyze_streaming(
        self,
        input_data: HivemindInput,
        max_debate_rounds: int = 5,
    ):
        """Run analysis and yield progress events.

        Yields event dicts. The final event has type "complete" and
        includes "output": HivemindOutput.
        """
        yield from run_debate_streaming(
            input_data=input_data,
            llm=self.llm,
            vector_store=self.vector_store,
            storage=self.storage,
            max_rounds=max_debate_rounds,
        )

    def execute_single_agent(
        self,
        agent: AgentDefinition,
        query: str,
    ) -> tuple[AgentExecutionResult, AuditEvent]:
        """Execute a single agent without the full debate process."""
        return execute_agent(
            agent=agent,
            query=query,
            llm=self.llm,
            vector_store=self.vector_store,
            storage=self.storage,
        )

    def run_simulation(
        self,
        formula: SimulationFormula,
        inputs: dict,
    ) -> dict:
        """Run a simulation formula with given inputs."""
        return run_simulation(formula, inputs)

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        """Get an agent definition by ID."""
        return self.storage.get_agent(agent_id)

    def list_agents(self) -> list[AgentDefinition]:
        """List all available agents."""
        return self.storage.list_agents()


# ---------------------------------------------------------------------------
# Factory function for common setups
# ---------------------------------------------------------------------------


def create_engine(
    anthropic_api_key: str,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
) -> HivemindEngine:
    """Create a HivemindEngine with Claude as the LLM."""
    from hivemind_core.llm import ClaudeLLM

    llm = ClaudeLLM(api_key=anthropic_api_key)
    return HivemindEngine(llm=llm, vector_store=vector_store, storage=storage)
