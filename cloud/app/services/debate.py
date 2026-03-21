"""Debate engine service - thin wrapper around Hivemind core.

This module provides backwards compatibility with the existing FastAPI
routes while delegating to the platform-agnostic hivemind_core package.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings
from hivemind_core import ClaudeLLM, HivemindInput
from hivemind_core import run_debate as core_run_debate
from hivemind_core.adapters import QdrantVectorStore, SQLAlchemyStorage

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def run_debate(
    db: "Session",
    problem_statement: str,
    theory_agent_ids: list[str],
    practicality_agent_ids: list[str] | None = None,
    sufficiency_value: int = 1,
    feasibility_threshold: int = 80,
    max_rounds: int = 5,
) -> dict:
    """Run the full multi-agent debate process.

    This is a thin wrapper that delegates to hivemind_core while
    maintaining backwards compatibility with the existing API.

    Args:
        db: SQLAlchemy database session
        problem_statement: The query to analyze
        theory_agent_ids: IDs of theory agents to use
        practicality_agent_ids: IDs of practicality agents (optional)
        sufficiency_value: Target number of recommendations
        feasibility_threshold: Minimum score for recommendations
        max_rounds: Maximum debate iterations

    Returns:
        Dict with recommendations, audit trail, and metadata
    """
    # Create core interfaces
    llm = ClaudeLLM(api_key=settings.ANTHROPIC_API_KEY)
    storage = SQLAlchemyStorage(db)
    vector_store = QdrantVectorStore(
        qdrant_url=settings.VECTOR_DB_URL,
        embedding_model=settings.EMBEDDING_MODEL,
        db=db,
    )

    # Build input
    input_data = HivemindInput(
        query=problem_statement,
        theory_agent_ids=theory_agent_ids,
        practicality_agent_ids=practicality_agent_ids or [],
        sufficiency_value=sufficiency_value,
        feasibility_threshold=feasibility_threshold,
    )

    # Run debate via core
    output = core_run_debate(
        input_data=input_data,
        llm=llm,
        vector_store=vector_store,
        storage=storage,
        max_rounds=max_rounds,
    )

    # Convert to dict for backwards compatibility
    recommendations = []
    for rec in output.recommendations:
        recommendations.append({
            "id": rec.id,
            "title": rec.title,
            "content": rec.content,
            "reasoning": rec.reasoning,
            "contributing_agents": rec.contributing_agents,
            "retrieved_chunk_ids": rec.retrieved_chunk_ids,
            "feasibility_scores": [
                {
                    "agent_id": fs.agent_id,
                    "agent_name": fs.agent_name,
                    "score": fs.score,
                    "risks": fs.risks,
                    "challenges": fs.challenges,
                    "mitigations": fs.mitigations,
                    "reasoning": fs.reasoning,
                }
                for fs in rec.feasibility_scores
            ],
            "average_feasibility": rec.average_feasibility,
            "suggested_actions": [
                {
                    "type": str(action.type),
                    "target": action.target,
                    "payload": action.payload,
                    "description": action.description,
                }
                for action in rec.suggested_actions
            ],
        })

    audit_trail = []
    for event in output.audit_trail:
        audit_trail.append({
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "agent_id": event.agent_id,
            "retrieved_chunk_ids": event.retrieved_chunk_ids,
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "latency_ms": event.latency_ms,
            "details": event.details,
        })

    return {
        "id": output.id,
        "recommendations": recommendations,
        "vetoed_solutions": [
            {
                "id": rec.id,
                "title": rec.title,
                "content": rec.content,
                "average_feasibility": rec.average_feasibility,
            }
            for rec in output.vetoed_solutions
        ],
        "audit_trail": audit_trail,
        "suggested_actions": [
            {
                "type": str(action.type),
                "target": action.target,
                "payload": action.payload,
                "description": action.description,
            }
            for action in output.suggested_actions
        ],
        "debate_rounds": output.debate_rounds,
        "duration_ms": output.duration_ms,
        "total_tokens": output.total_tokens,
    }
