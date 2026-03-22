"""
PostgreSQL storage adapter implementing Hivemind Core StorageInterface.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent import AgentDefinition
from app.models.knowledge_document import KnowledgeDocument
from app.models.simulation_formula import SimulationFormula
from app.models.text_chunk import TextChunk as TextChunkModel
from hivemind_core.interfaces import StorageInterface
from hivemind_core.types import (
    AgentConfig,
    RagConfig,
    SimulationConfig,
    SimulationIO,
    TextChunk,
)


def agent_from_orm(agent: AgentDefinition) -> AgentConfig:
    """Convert ORM AgentDefinition to AgentConfig for use with HivemindEngine."""
    return _agent_to_config(agent)


def _agent_to_config(agent: AgentDefinition) -> AgentConfig:
    """Convert ORM AgentDefinition to AgentConfig dataclass."""
    rag_config_data = agent.rag_config or {}
    return AgentConfig(
        id=agent.id,
        name=agent.name,
        network_type=agent.network_type,
        description=agent.description or "",
        framework=agent.framework or "",
        principles=agent.principles or "",
        analytical_style=agent.analytical_style or "",
        scoring_criteria=agent.scoring_criteria or "",
        score_interpretation=agent.score_interpretation or "",
        knowledge_base_ids=agent.knowledge_base_ids or [],
        simulation_formula_ids=agent.simulation_formula_ids or [],
        rag_config=RagConfig(
            chunks_to_retrieve=rag_config_data.get("chunks_to_retrieve", 8),
            similarity_threshold=rag_config_data.get("similarity_threshold", 0.0),
            use_reranking=rag_config_data.get("use_reranking", False),
        ),
        status=agent.status,
        version=agent.version,
    )


def _simulation_to_config(sim: SimulationFormula) -> SimulationConfig:
    """Convert ORM SimulationFormula to SimulationConfig dataclass."""
    inputs = [
        SimulationIO(
            name=io.get("name", ""),
            description=io.get("description", ""),
            unit=io.get("unit", ""),
            default_value=io.get("default_value"),
        )
        for io in (sim.inputs or [])
    ]
    outputs = [
        SimulationIO(
            name=io.get("name", ""),
            description=io.get("description", ""),
            unit=io.get("unit", ""),
            default_value=io.get("default_value"),
        )
        for io in (sim.outputs or [])
    ]
    return SimulationConfig(
        id=sim.id,
        name=sim.name,
        description=sim.description or "",
        simulation_type=sim.simulation_type or "formula",
        inputs=inputs,
        calculations=sim.calculations,
        outputs=outputs,
        code=sim.code,
        tags=sim.tags or [],
    )


def _chunk_to_dataclass(chunk: TextChunkModel, document_name: str = "") -> TextChunk:
    """Convert ORM TextChunk to TextChunk dataclass."""
    return TextChunk(
        id=chunk.id,
        content=chunk.content,
        document_id=chunk.document_id,
        document_name=document_name,
        knowledge_base_id=chunk.knowledge_base_id,
        source_page=chunk.source_page,
        token_count=chunk.token_count,
    )


class PostgresStorage(StorageInterface):
    """PostgreSQL implementation of StorageInterface."""

    def __init__(self, db: Session):
        self.db = db

    def get_agent(self, agent_id: str) -> AgentConfig | None:
        agent = self.db.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()
        if not agent:
            return None
        return _agent_to_config(agent)

    def get_agents(self, agent_ids: list[str]) -> list[AgentConfig]:
        agents = self.db.query(AgentDefinition).filter(AgentDefinition.id.in_(agent_ids)).all()
        return [_agent_to_config(a) for a in agents]

    def get_simulation(self, simulation_id: str) -> SimulationConfig | None:
        sim = self.db.query(SimulationFormula).filter(SimulationFormula.id == simulation_id).first()
        if not sim:
            return None
        return _simulation_to_config(sim)

    def get_simulations(self, simulation_ids: list[str]) -> list[SimulationConfig]:
        sims = self.db.query(SimulationFormula).filter(SimulationFormula.id.in_(simulation_ids)).all()
        return [_simulation_to_config(s) for s in sims]

    def get_chunk(self, chunk_id: str) -> TextChunk | None:
        chunk = self.db.query(TextChunkModel).filter(TextChunkModel.id == chunk_id).first()
        if not chunk:
            return None

        # Get document name
        doc = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id == chunk.document_id).first()
        document_name = doc.filename if doc else ""

        return _chunk_to_dataclass(chunk, document_name)

    def get_chunks(self, chunk_ids: list[str]) -> list[TextChunk]:
        chunks = self.db.query(TextChunkModel).filter(TextChunkModel.id.in_(chunk_ids)).all()

        # Get all document names
        document_ids = {c.document_id for c in chunks}
        docs = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id.in_(document_ids)).all()
        doc_names = {d.id: d.filename for d in docs}

        return [_chunk_to_dataclass(c, doc_names.get(c.document_id, "")) for c in chunks]

    def get_documents_for_knowledge_bases(
        self, kb_ids: list[str]
    ) -> list[dict]:
        """Return list of dicts with keys: document_id, knowledge_base_id, filename, token_count."""
        if not kb_ids:
            return []

        token_totals = (
            self.db.query(
                TextChunkModel.document_id,
                TextChunkModel.knowledge_base_id,
                func.sum(TextChunkModel.token_count).label("total_tokens"),
            )
            .filter(TextChunkModel.knowledge_base_id.in_(kb_ids))
            .group_by(TextChunkModel.document_id, TextChunkModel.knowledge_base_id)
            .all()
        )

        doc_ids = [row.document_id for row in token_totals]
        docs = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id.in_(doc_ids)).all()
        doc_names = {d.id: d.filename for d in docs}

        return [
            {
                "document_id": row.document_id,
                "knowledge_base_id": row.knowledge_base_id,
                "filename": doc_names.get(row.document_id, ""),
                "token_count": int(row.total_tokens),
            }
            for row in token_totals
        ]

    def get_documents_by_knowledge_base(
        self, knowledge_base_ids: list[str]
    ) -> list[tuple[str, int]]:
        """List documents in the given KB(s) with per-document token count (sum of chunk tokens)."""
        if not knowledge_base_ids:
            return []

        token_totals = (
            self.db.query(
                TextChunkModel.document_id,
                func.sum(TextChunkModel.token_count).label("total_tokens"),
            )
            .filter(TextChunkModel.knowledge_base_id.in_(knowledge_base_ids))
            .group_by(TextChunkModel.document_id)
            .all()
        )
        return [(row.document_id, int(row.total_tokens)) for row in token_totals]
