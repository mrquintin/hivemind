from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisRequest(BaseModel):
    """Request to run a strategic analysis.

    Attributes:
        problem_statement: Textual description of the problem to analyze.
        analysis_mode: "simple" (default) or "full".
        effort_level: "low", "medium" (default), or "high".
        sufficiency_value: Target number of aggregate conclusions (1-10).
        feasibility_threshold: 1-100 threshold for practicality pass/fail.
    """
    problem_statement: str
    analysis_mode: str = Field(
        default="simple",
        description='Execution mode: "simple" (fast baseline) or "full" (deeper synthesis)',
    )
    effort_level: str = Field(
        default="medium",
        description='Effort tier: "low", "medium", or "high"',
    )
    context_documents: list[str] = Field(default_factory=list)
    context_document_texts: list[str] = Field(
        default_factory=list,
        description="Raw text snippets (client-cleared) to include as context"
    )
    sufficiency_value: int = Field(default=1, ge=1, le=10)
    feasibility_threshold: int = Field(default=80, ge=1, le=100)

    # Budget overrides (optional — effort_level provides defaults)
    max_total_llm_calls: int | None = Field(default=None, description="Hard cap on LLM calls")
    max_total_tokens: int | None = Field(default=None, description="Hard cap on total tokens")
    max_wallclock_ms: int | None = Field(default=None, description="Hard cap on wall-clock ms")
    max_repair_iterations: int = Field(default=2, ge=0, le=10)

    # Legacy fields — kept optional for backward compatibility
    theory_network_density: int | None = Field(
        default=None,
        description="Token count per theory unit for dynamic KB distribution"
    )
    enabled_theory_agent_ids: list[str] = Field(default_factory=list)
    enabled_practicality_agent_ids: list[str] = Field(default_factory=list)
    max_veto_restarts: int = Field(default=3, ge=0, le=10)
    similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    revision_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    practicality_criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    use_case_profile: str | None = Field(default=None, description="Resolve practicality agents by profile")
    decision_type: str | None = Field(default=None, description="Resolve theory agents by decision type")

    @field_validator("analysis_mode")
    @classmethod
    def validate_analysis_mode(cls, v: str) -> str:
        if v not in ("simple", "full"):
            raise ValueError(f'analysis_mode must be "simple" or "full", got "{v}"')
        return v

    @field_validator("effort_level")
    @classmethod
    def validate_effort_level(cls, v: str) -> str:
        if v not in ("low", "medium", "high"):
            raise ValueError(f'effort_level must be "low", "medium", or "high", got "{v}"')
        return v


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
    status: str = "approved"
    repair_history: list[dict[str, Any]] = Field(default_factory=list)
    partial_scoring: bool = False


class BudgetUsageOut(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wallclock_ms: int = 0


class RepairStatsOut(BaseModel):
    recommendations_repaired: int = 0
    recommendations_recovered: int = 0
    recommendations_failed_after_repairs: int = 0
    total_repair_iterations: int = 0


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
    termination_reason: str = ""
    budget_usage: BudgetUsageOut = Field(default_factory=BudgetUsageOut)
    mode_used: str = "simple"
    repair_stats: RepairStatsOut = Field(default_factory=RepairStatsOut)
