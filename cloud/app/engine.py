"""
Hivemind engine factory - single entry point for creating the analysis engine.

Use this module to obtain a HivemindEngine configured with the app's adapters
(Claude, Qdrant, PostgreSQL). All analysis flows (REST, WebSocket, agent test)
should use this factory for consistency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.llm import ClaudeAdapter
from app.adapters.storage import PostgresStorage
from app.adapters.vector_db import QdrantVectorDB
from hivemind_core import HivemindEngine

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def create_engine(db: "Session") -> HivemindEngine:
    """Create a HivemindEngine with app-configured adapters.

    Args:
        db: SQLAlchemy database session for storage

    Returns:
        Configured HivemindEngine ready for analysis
    """
    return HivemindEngine(
        llm=ClaudeAdapter(),
        vector_store=QdrantVectorDB(),
        storage=PostgresStorage(db),
    )
