"""Agent execution service - thin wrapper around Hivemind engine.

Delegates to the app engine factory for consistent adapter usage.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.storage import agent_from_orm
from app.engine import create_engine

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.agent import AgentDefinition


def execute_agent(db: "Session", agent: "AgentDefinition", problem_statement: str) -> dict:
    """Execute a single agent against a problem statement.

    Args:
        db: SQLAlchemy database session
        agent: Agent definition (SQLAlchemy model)
        problem_statement: The query to analyze

    Returns:
        Dict with agent response and metadata
    """
    engine = create_engine(db)
    agent_def = agent_from_orm(agent)
    result, _audit = engine.execute_single_agent(agent_def, problem_statement)

    return {
        "agent_id": result.agent_id,
        "agent_name": result.agent_name,
        "network_type": result.network_type,
        "response": result.response,
        "retrieved_chunk_ids": result.retrieved_chunk_ids,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        "raw_response": result.raw_response,
    }
