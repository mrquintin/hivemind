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
        theory_agent_ids: Specific theory agent IDs to use (if not using density-based distribution).
        practicality_agent_ids: Practicality agent IDs for feasibility evaluation.
        sufficiency_value: Target number of aggregate conclusions. The debate process
            continues until the number of unique aggregated conclusions drops to or
            below this value.
        feasibility_threshold: 1-100 threshold. If the average feasibility score across
            all practicality agents is equal to or lower than this value, the entire
            solution list is vetoed and the theory network must restart from scratch.
        theory_network_density: Token count target per theory network unit. Determines
            how knowledge base documents are distributed across dynamically created
            units. Range: min_doc_tokens to sum_all_doc_tokens. When set, the system
            will create units dynamically based on this value rather than using
            pre-defined theory agents.
        max_veto_restarts: Maximum number of times the theory network can restart
            after a veto before giving up. Default is 3.
        metadata: Additional metadata for the analysis.
    """

    query: str
    context: list[ContextItem] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    theory_agent_ids: list[str] = field(default_factory=list)
    practicality_agent_ids: list[str] = field(default_factory=list)
    sufficiency_value: int = 1
    feasibility_threshold: int = 80
    theory_network_density: int | None = None
    max_veto_restarts: int = 3
    similarity_threshold: float = 0.65
    revision_strength: float = 0.5
    practicality_criticality: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


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
