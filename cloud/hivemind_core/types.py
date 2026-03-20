"""Platform-agnostic data types for Hivemind core.

These types are used throughout the core engine and can be serialized
for any transport layer (REST, WebSocket, MQTT, gRPC, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ContextType(str, Enum):
    TEXT = "text"
    SENSOR = "sensor"
    IMAGE = "image"
    AUDIO_TRANSCRIPT = "audio_transcript"
    DOCUMENT = "document"
    STRUCTURED = "structured"


class ActionType(str, Enum):
    ALERT = "alert"
    ADJUST_SETTING = "adjust_setting"
    NOTIFY = "notify"
    LOG = "log"
    EXECUTE = "execute"
    CONFIRM = "confirm"


class NetworkType(str, Enum):
    THEORY = "theory"
    PRACTICALITY = "practicality"


class AgentStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AnalysisMode(str, Enum):
    SIMPLE = "simple"
    FULL = "full"


class EffortLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TerminationReason(str, Enum):
    # Simple mode
    SIMPLE_COMPLETED = "simple_completed"
    # Full mode
    SUFFICIENCY_REACHED = "sufficiency_reached"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    STAGNATION_EARLY_STOP = "stagnation_early_stop"
    COMPLETED_WITH_REPAIRS = "completed_with_repairs"
    GLOBAL_RESTART_EXHAUSTED = "global_restart_exhausted"
    # Shared
    BUDGET_EXHAUSTED = "budget_exhausted"
    VALIDATION_ERROR = "validation_error"


class RecommendationStatus(str, Enum):
    APPROVED = "approved"
    VETOED = "vetoed"
    FAILED_AFTER_REPAIRS = "failed_after_repairs"


# ---------------------------------------------------------------------------
# Effort-level defaults
# ---------------------------------------------------------------------------

EFFORT_DEFAULTS: dict[str, dict[str, int]] = {
    "low": {
        "max_rounds": 2,
        "max_repair_iterations": 1,
        "max_total_llm_calls": 30,
    },
    "medium": {
        "max_rounds": 4,
        "max_repair_iterations": 2,
        "max_total_llm_calls": 80,
    },
    "high": {
        "max_rounds": 6,
        "max_repair_iterations": 3,
        "max_total_llm_calls": 160,
    },
}


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


@dataclass
class BudgetUsage:
    """Tracks resource consumption during an analysis run."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wallclock_ms: int = 0


@dataclass
class RepairStats:
    """Statistics about the recommendation repair process."""

    recommendations_repaired: int = 0
    recommendations_recovered: int = 0
    recommendations_failed_after_repairs: int = 0
    total_repair_iterations: int = 0


class BudgetExhausted(Exception):
    """Raised when a budget ceiling is exceeded."""
    pass


# ---------------------------------------------------------------------------
# Input Types
# ---------------------------------------------------------------------------


@dataclass
class ContextItem:
    """A piece of context fed to Hivemind (document, sensor reading, etc.)."""

    type: ContextType | str
    content: str | bytes | dict[str, Any]
    source: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HivemindInput:
    """Standard input to the Hivemind engine.

    Attributes:
        query: Textual description of the problem to analyze.
        context: Additional context items (documents, sensor data, etc.).
        agent_ids: Legacy field for backward compatibility.
        theory_agent_ids: Specific theory agent IDs to use.
        practicality_agent_ids: Practicality agent IDs for feasibility evaluation.
        analysis_mode: "simple" (default) or "full".
        effort_level: "low", "medium" (default), or "high".
        sufficiency_value: Target number of aggregate conclusions.
        feasibility_threshold: 1-100 threshold for feasibility pass/fail.
        max_total_llm_calls: Hard cap on LLM calls (None = use effort default).
        max_total_tokens: Hard cap on total tokens (None = unlimited).
        max_wallclock_ms: Hard cap on wall-clock time (None = unlimited).
        max_repair_iterations: Max repair attempts per failed recommendation.
        stagnation_window_rounds: Rounds to look back for improvement.
        min_aggregation_improvement: Min reduction in aggregated count to avoid stagnation.
        theory_network_density: Token count per theory unit for dynamic distribution.
        max_veto_restarts: Max global restarts (full mode only, capped at 1 by default).
        similarity_threshold: Legacy field, kept for backward compat.
        revision_strength: Legacy field, kept for backward compat.
        practicality_criticality: Legacy field, kept for backward compat.
        metadata: Additional metadata for the analysis.
    """

    query: str
    context: list[ContextItem] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    theory_agent_ids: list[str] = field(default_factory=list)
    practicality_agent_ids: list[str] = field(default_factory=list)
    analysis_mode: str = "simple"
    effort_level: str = "medium"
    sufficiency_value: int = 1
    feasibility_threshold: int = 80
    max_total_llm_calls: int | None = None
    max_total_tokens: int | None = None
    max_wallclock_ms: int | None = None
    max_repair_iterations: int = 2
    stagnation_window_rounds: int = 2
    min_aggregation_improvement: int = 1
    theory_network_density: int | None = None
    max_veto_restarts: int = 3
    similarity_threshold: float = 0.65
    revision_strength: float = 0.5
    practicality_criticality: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_effective_max_rounds(self) -> int:
        """Return max debate rounds based on effort level."""
        defaults = EFFORT_DEFAULTS.get(self.effort_level, EFFORT_DEFAULTS["medium"])
        return defaults["max_rounds"]

    def get_effective_max_repair_iterations(self) -> int:
        """Return max repair iterations, preferring explicit over effort default."""
        defaults = EFFORT_DEFAULTS.get(self.effort_level, EFFORT_DEFAULTS["medium"])
        return self.max_repair_iterations if self.max_repair_iterations != 2 else defaults["max_repair_iterations"]

    def get_effective_max_llm_calls(self) -> int:
        """Return max LLM calls, preferring explicit over effort default."""
        if self.max_total_llm_calls is not None:
            return self.max_total_llm_calls
        defaults = EFFORT_DEFAULTS.get(self.effort_level, EFFORT_DEFAULTS["medium"])
        return defaults["max_total_llm_calls"]


# ---------------------------------------------------------------------------
# Agent / Knowledge Types
# ---------------------------------------------------------------------------


@dataclass
class RagConfig:
    """RAG retrieval configuration."""

    chunks_to_retrieve: int = 8
    similarity_threshold: float = 0.0
    use_reranking: bool = False


@dataclass
class AgentDefinition:
    """Platform-agnostic agent definition."""

    id: str
    name: str
    network_type: NetworkType | str
    description: str | None = None

    framework: str | None = None
    principles: str | None = None
    analytical_style: str | None = None

    scoring_criteria: str | None = None
    score_interpretation: str | None = None

    knowledge_base_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    simulation_formula_ids: list[str] = field(default_factory=list)
    rag_config: RagConfig = field(default_factory=RagConfig)

    status: AgentStatus | str = AgentStatus.DRAFT
    version: int = 1
    created_by: str | None = None


@dataclass
class RetrievedChunk:
    """A chunk of knowledge retrieved via RAG."""

    id: str
    content: str
    score: float
    document_name: str = "unknown"
    source_page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationIO:
    """Input or output definition for a simulation formula."""

    name: str
    description: str | None = None
    unit: str | None = None
    default_value: float | int | str | None = None


@dataclass
class SimulationFormula:
    """A mathematical formula for simulations."""

    id: str
    name: str
    description: str | None = None
    inputs: list[SimulationIO] = field(default_factory=list)
    calculations: str = ""
    outputs: list[SimulationIO] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Debate Process Types
# ---------------------------------------------------------------------------


@dataclass
class TheoryUnitSolution:
    """A solution generated by a theory network unit."""

    unit_id: str
    unit_name: str
    solution: str
    reasoning: str
    knowledge_base_ids: list[str] = field(default_factory=list)
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    revision_count: int = 0


@dataclass
class Critique:
    """A critique of one unit's solution by another unit."""

    source_unit_id: str
    target_unit_id: str
    critique_text: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class AggregatedSolution:
    """Multiple similar solutions aggregated by the Monitor.

    The Monitor groups similar solutions together and lists all their
    theoretical justifications side-by-side.
    """

    id: str
    merged_solution: str
    contributing_units: list[str] = field(default_factory=list)
    justifications: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    cluster_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DynamicTheoryUnit:
    """A dynamically created theory network unit based on density distribution.

    Created when theory_network_density is specified in the input.
    Each unit receives a portion of the knowledge base documents such that
    the total token count approximately matches the density value.
    """

    id: str
    name: str
    assigned_document_ids: list[str] = field(default_factory=list)
    total_tokens: int = 0
    framework: str = "Strategic Analysis"
    principles: str = "Analyze from available knowledge base perspective"


# ---------------------------------------------------------------------------
# Output Types
# ---------------------------------------------------------------------------


@dataclass
class Action:
    """A device-actionable item returned by Hivemind."""

    type: ActionType | str
    target: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    requires_confirmation: bool = False


@dataclass
class FeasibilityScore:
    """Feasibility evaluation from a practicality agent."""

    agent_id: str
    agent_name: str
    score: int
    risks: list[str] = field(default_factory=list)
    challenges: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    reasoning: str = ""
    retrieved_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    """A strategic recommendation produced by the engine."""

    id: str
    title: str
    content: str
    reasoning: str = ""
    contributing_agents: list[str] = field(default_factory=list)
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    feasibility_scores: list[FeasibilityScore] = field(default_factory=list)
    average_feasibility: float = 0.0
    suggested_actions: list[Action] = field(default_factory=list)
    status: str = "approved"
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    partial_scoring: bool = False


@dataclass
class AuditEvent:
    """An event in the audit trail."""

    timestamp: datetime
    event_type: str
    agent_id: str | None = None
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentExecutionResult:
    """Result of executing a single agent."""

    agent_id: str
    agent_name: str
    network_type: str
    response: str
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class HivemindOutput:
    """Standard output from the Hivemind engine."""

    id: str
    recommendations: list[Recommendation] = field(default_factory=list)
    vetoed_solutions: list[Recommendation] = field(default_factory=list)
    audit_trail: list[AuditEvent] = field(default_factory=list)
    suggested_actions: list[Action] = field(default_factory=list)
    debate_rounds: int = 0
    veto_restarts: int = 0
    aggregated_solution_count: int = 0
    theory_units_created: int = 0
    duration_ms: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    termination_reason: str = ""
    budget_usage: BudgetUsage = field(default_factory=BudgetUsage)
    mode_used: str = "simple"
    repair_stats: RepairStats = field(default_factory=RepairStats)


# ---------------------------------------------------------------------------
# Storage Interfaces (for dependency injection)
# ---------------------------------------------------------------------------


class StorageInterface:
    """Abstract interface for persistent storage."""

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        raise NotImplementedError

    def list_agents(self, status: AgentStatus | None = None) -> list[AgentDefinition]:
        raise NotImplementedError

    def get_simulation(self, formula_id: str) -> SimulationFormula | None:
        raise NotImplementedError

    def get_simulations(self, formula_ids: list[str]) -> list[SimulationFormula]:
        raise NotImplementedError

    def get_documents_for_knowledge_bases(self, kb_ids: list[str]) -> list[dict]:
        """Return list of dicts with keys: document_id, knowledge_base_id, filename, token_count."""
        raise NotImplementedError


class VectorStoreInterface:
    """Abstract interface for vector database operations."""

    def retrieve(
        self,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int = 8,
        similarity_threshold: float = 0.0,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError

    def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[dict],
    ) -> None:
        raise NotImplementedError


class LLMInterface:
    """Abstract interface for LLM calls."""

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Backward-Compatibility Aliases
# ---------------------------------------------------------------------------

# These aliases exist for code that imports the old names.
AgentConfig = AgentDefinition
SimulationConfig = SimulationFormula
TextChunk = RetrievedChunk
