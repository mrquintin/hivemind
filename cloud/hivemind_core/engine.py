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
        >>> input_data = HivemindInput(query="Should we expand to Europe?", ...)
        >>> output = engine.analyze(input_data)
    """

    def __init__(
        self,
        llm: LLMInterface,
        vector_store: VectorStoreInterface,
        storage: StorageInterface,
    ):
        """Initialize the Hivemind engine.

        Args:
            llm: LLM interface for AI calls
            vector_store: Vector store for RAG retrieval
            storage: Storage interface for agents and simulations
        """
        self.llm = llm
        self.vector_store = vector_store
        self.storage = storage

    def analyze(
        self,
        input_data: HivemindInput,
        max_debate_rounds: int = 5,
    ) -> HivemindOutput:
        """Run a full strategic analysis with the debate engine.

        Args:
            input_data: The input query and configuration
            max_debate_rounds: Maximum debate iterations

        Returns:
            HivemindOutput with recommendations and audit trail
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
        """Run analysis and yield progress events (debate_start, initial_solutions, round_start, complete, etc.).

        Yields event dicts. The final event has type "complete" and includes "output": HivemindOutput.
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
        """Execute a single agent without the full debate process.

        Useful for testing agents or simple single-agent queries.

        Args:
            agent: The agent definition
            query: The problem statement

        Returns:
            Tuple of (AgentExecutionResult, AuditEvent)
        """
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
        """Run a simulation formula with given inputs.

        Args:
            formula: The simulation formula definition
            inputs: Input values for the formula

        Returns:
            Dict with 'outputs' and 'variables'
        """
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
    """Create a HivemindEngine with Claude as the LLM.

    This is a convenience factory for the most common setup.

    Args:
        anthropic_api_key: Anthropic API key for Claude
        vector_store: Vector store implementation
        storage: Storage implementation

    Returns:
        Configured HivemindEngine instance
    """
    from hivemind_core.llm import ClaudeLLM

    llm = ClaudeLLM(api_key=anthropic_api_key)
    return HivemindEngine(llm=llm, vector_store=vector_store, storage=storage)
