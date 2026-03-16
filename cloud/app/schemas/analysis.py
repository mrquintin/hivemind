from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """Request to run a strategic analysis.
    
    Attributes:
        problem_statement: Textual description of the problem to analyze.
        context_documents: Additional document IDs to include as context.
        sufficiency_value: Target number of aggregate conclusions (1-10).
            The debate process continues until unique conclusions <= this value.
        feasibility_threshold: 1-100 threshold for practicality veto.
            If avg feasibility across all practicality agents <= this value,
            the entire solution list is vetoed and theory network restarts.
        theory_network_density: Token count per theory unit for dynamic distribution.
            When set, knowledge base documents are distributed across dynamically
            created units. When None, uses the specified theory agents directly.
        enabled_theory_agent_ids: Specific theory agent IDs to use (when not using density).
        enabled_practicality_agent_ids: Practicality agent IDs for feasibility evaluation.
        max_veto_restarts: Max times theory network can restart after veto (default 3).
    """
    problem_statement: str
    context_documents: list[str] = Field(default_factory=list)
    context_document_texts: list[str] = Field(
        default_factory=list,
        description="Raw text snippets (client-cleared) to include as context"
    )
    sufficiency_value: int = Field(default=1, ge=1, le=10)
    feasibility_threshold: int = Field(default=80, ge=1, le=100)
    theory_network_density: int | None = Field(
        default=None,
        description="Token count per theory unit for dynamic KB distribution"
    )
    enabled_theory_agent_ids: list[str] = Field(default_factory=list)
    enabled_practicality_agent_ids: list[str] = Field(default_factory=list)
    max_veto_restarts: int = Field(default=3, ge=1, le=10)
    similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    revision_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    practicality_criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    use_case_profile: str | None = Field(default=None, description="Resolve practicality agents by profile (e.g. small_business, individual_career)")
    decision_type: str | None = Field(default=None, description="Resolve strategic KBs/theory agents by decision type (e.g. market_entry, m_and_a)")


class AgentExecutionOut(BaseModel):
    agent_id: str
    agent_name: str
    network_type: str
    response: str
    retrieved_chunk_ids: list[str]
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class FeasibilityScoreOut(BaseModel):
    agent_id: str
    agent_name: str
    score: int
    risks: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    reasoning: str = ""


class RecommendationOut(BaseModel):
    id: str
    title: str
    content: str
    reasoning: str = ""
    contributing_agents: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    feasibility_scores: list[FeasibilityScoreOut] = Field(default_factory=list)
    average_feasibility: float = 0.0


class AnalysisResultOut(BaseModel):
    id: str
    recommendations: list[RecommendationOut]
    vetoed_solutions: list[RecommendationOut] = Field(default_factory=list)
    audit_trail: list[dict]
    debate_rounds: int = 0
    veto_restarts: int = 0
    theory_units_created: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
