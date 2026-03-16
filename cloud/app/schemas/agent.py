from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RagConfig(BaseModel):
    chunks_to_retrieve: int = 8
    similarity_threshold: float = 0.0
    use_reranking: bool = False


class AgentCreate(BaseModel):
    name: str
    network_type: str
    description: str | None = None

    framework: str | None = None
    principles: str | None = None
    analytical_style: str | None = None

    scoring_criteria: str | None = None
    score_interpretation: str | None = None

    knowledge_base_ids: list[str] = Field(default_factory=list)
    rag_config: RagConfig = Field(default_factory=RagConfig)
    simulation_formula_ids: list[str] = Field(default_factory=list)

    status: str = "draft"
    use_case_profile: str | None = None
    version: int = 1
    created_by: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    network_type: str | None = None
    description: str | None = None

    framework: str | None = None
    principles: str | None = None
    analytical_style: str | None = None

    scoring_criteria: str | None = None
    score_interpretation: str | None = None

    knowledge_base_ids: list[str] | None = None
    rag_config: RagConfig | None = None
    simulation_formula_ids: list[str] | None = None

    status: str | None = None
    use_case_profile: str | None = None
    version: int | None = None


class AgentOut(BaseModel):
    id: str
    name: str
    network_type: str
    description: str | None = None

    framework: str | None = None
    principles: str | None = None
    analytical_style: str | None = None

    scoring_criteria: str | None = None
    score_interpretation: str | None = None

    knowledge_base_ids: list[str]
    rag_config: dict[str, Any]
    simulation_formula_ids: list[str]

    status: str
    use_case_profile: str | None = None
    version: int
    created_by: str | None = None

    class Config:
        from_attributes = True


class AgentTestRequest(BaseModel):
    problem_statement: str
