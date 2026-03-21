"""Hivemind Core - Platform-agnostic strategic analysis engine.

This package provides the core intelligence layer for Hivemind,
including multi-agent debate, RAG retrieval, and simulation execution.

It can be used from any transport layer (REST, WebSocket, MQTT, gRPC)
or embedded directly into applications.

Example:
    >>> from hivemind_core import HivemindEngine, HivemindInput, create_engine
    >>> engine = create_engine(api_key="...", vector_store=vs, storage=store)
    >>> output = engine.analyze(HivemindInput(query="Should we expand?"))
"""

from hivemind_core.agents import (
    build_practicality_prompt,
    build_theory_prompt,
    execute_agent,
)
from hivemind_core.debate import run_debate, run_debate_streaming
from hivemind_core.engine import HivemindEngine, create_engine
from hivemind_core.llm import ClaudeLLM, MockLLM
from hivemind_core.rag import format_chunks_for_prompt, retrieve_chunks
from hivemind_core.simulations import (
    format_simulations_for_prompt,
    run_simulation,
)
from hivemind_core.types import (
    EFFORT_DEFAULTS,
    Action,
    ActionType,
    AgentDefinition,
    AgentExecutionResult,
    AgentStatus,
    AnalysisMode,
    AuditEvent,
    BudgetExhausted,
    BudgetUsage,
    ContextItem,
    ContextType,
    EffortLevel,
    FeasibilityScore,
    HivemindInput,
    HivemindOutput,
    LLMInterface,
    NetworkType,
    RagConfig,
    Recommendation,
    RecommendationStatus,
    RepairStats,
    RetrievedChunk,
    SimulationFormula,
    SimulationIO,
    StorageInterface,
    TerminationReason,
    VectorStoreInterface,
)

__version__ = "0.1.0"

__all__ = [
    # Engine
    "HivemindEngine",
    "create_engine",
    # Core functions
    "run_debate",
    "run_debate_streaming",
    "execute_agent",
    "run_simulation",
    "retrieve_chunks",
    # Prompt builders
    "build_theory_prompt",
    "build_practicality_prompt",
    "format_chunks_for_prompt",
    "format_simulations_for_prompt",
    # LLM implementations
    "ClaudeLLM",
    "MockLLM",
    # Types - Input/Output
    "HivemindInput",
    "HivemindOutput",
    "ContextItem",
    "ContextType",
    "Action",
    "ActionType",
    "Recommendation",
    "FeasibilityScore",
    "AuditEvent",
    # Types - Mode/Budget/Repair
    "AnalysisMode",
    "EffortLevel",
    "TerminationReason",
    "RecommendationStatus",
    "BudgetUsage",
    "BudgetExhausted",
    "RepairStats",
    "EFFORT_DEFAULTS",
    # Types - Agents
    "AgentDefinition",
    "AgentStatus",
    "NetworkType",
    "AgentExecutionResult",
    "RagConfig",
    # Types - Knowledge
    "RetrievedChunk",
    "SimulationFormula",
    "SimulationIO",
    # Interfaces
    "LLMInterface",
    "StorageInterface",
    "VectorStoreInterface",
]
