"""SQLAlchemy-based storage adapter for Hivemind core."""
from __future__ import annotations

from typing import TYPE_CHECKING

from hivemind_core.types import (
    AgentDefinition,
    AgentStatus,
    RagConfig,
    SimulationFormula,
    SimulationIO,
    StorageInterface,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SQLAlchemyStorage(StorageInterface):
    """Storage adapter using SQLAlchemy ORM.

    This adapter bridges the Hivemind core to the existing
    FastAPI/SQLAlchemy models.
    """

    def __init__(self, db: "Session"):
        self.db = db

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        """Get an agent by ID."""
        from app.models.agent import AgentDefinition as AgentModel

        agent = self.db.query(AgentModel).filter(AgentModel.id == agent_id).first()
        if not agent:
            return None

        return self._agent_model_to_dataclass(agent)

    def list_agents(self, status: AgentStatus | None = None) -> list[AgentDefinition]:
        """List all agents, optionally filtered by status."""
        from app.models.agent import AgentDefinition as AgentModel

        query = self.db.query(AgentModel)
        if status:
            query = query.filter(AgentModel.status == str(status))
        agents = query.all()
        return [self._agent_model_to_dataclass(a) for a in agents]

    def get_simulation(self, formula_id: str) -> SimulationFormula | None:
        """Get a simulation formula by ID."""
        from app.models.simulation_formula import SimulationFormula as SimModel

        sim = self.db.query(SimModel).filter(SimModel.id == formula_id).first()
        if not sim:
            return None

        return self._simulation_model_to_dataclass(sim)

    def get_simulations(self, formula_ids: list[str]) -> list[SimulationFormula]:
        """Get multiple simulation formulas by ID."""
        if not formula_ids:
            return []

        from app.models.simulation_formula import SimulationFormula as SimModel

        sims = self.db.query(SimModel).filter(SimModel.id.in_(formula_ids)).all()
        return [self._simulation_model_to_dataclass(s) for s in sims]

    def get_documents_for_knowledge_bases(self, kb_ids: list[str]) -> list[dict]:
        """Return list of dicts with document_id, knowledge_base_id, filename, token_count."""
        if not kb_ids:
            return []
        from sqlalchemy import func

        from app.models.knowledge_document import KnowledgeDocument
        from app.models.text_chunk import TextChunk as TextChunkModel

        rows = (
            self.db.query(
                TextChunkModel.document_id,
                TextChunkModel.knowledge_base_id,
                func.sum(TextChunkModel.token_count).label("total_tokens"),
            )
            .filter(TextChunkModel.knowledge_base_id.in_(kb_ids))
            .group_by(TextChunkModel.document_id, TextChunkModel.knowledge_base_id)
            .all()
        )

        doc_ids = [r.document_id for r in rows]
        docs = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id.in_(doc_ids)).all()
        doc_names = {d.id: d.filename for d in docs}

        return [
            {
                "document_id": r.document_id,
                "knowledge_base_id": r.knowledge_base_id,
                "filename": doc_names.get(r.document_id, ""),
                "token_count": int(r.total_tokens),
            }
            for r in rows
        ]

    def _agent_model_to_dataclass(self, agent) -> AgentDefinition:
        """Convert SQLAlchemy model to core dataclass."""
        rag_config_data = agent.rag_config or {}
        rag_config = RagConfig(
            chunks_to_retrieve=rag_config_data.get("chunks_to_retrieve", 8),
            similarity_threshold=rag_config_data.get("similarity_threshold", 0.0),
            use_reranking=rag_config_data.get("use_reranking", False),
        )

        return AgentDefinition(
            id=agent.id,
            name=agent.name,
            network_type=agent.network_type,
            description=agent.description,
            framework=agent.framework,
            principles=agent.principles,
            analytical_style=agent.analytical_style,
            scoring_criteria=agent.scoring_criteria,
            score_interpretation=agent.score_interpretation,
            knowledge_base_ids=agent.knowledge_base_ids or [],
            simulation_formula_ids=getattr(agent, "simulation_formula_ids", []) or [],
            rag_config=rag_config,
            status=agent.status,
            version=agent.version,
            created_by=agent.created_by,
        )

    def _simulation_model_to_dataclass(self, sim) -> SimulationFormula:
        """Convert SQLAlchemy model to core dataclass."""
        inputs = []
        for entry in (sim.inputs or []):
            inputs.append(
                SimulationIO(
                    name=entry.get("name", ""),
                    description=entry.get("description"),
                    unit=entry.get("unit"),
                    default_value=entry.get("default_value"),
                )
            )

        outputs = []
        for entry in (sim.outputs or []):
            outputs.append(
                SimulationIO(
                    name=entry.get("name", ""),
                    description=entry.get("description"),
                    unit=entry.get("unit"),
                    default_value=entry.get("default_value"),
                )
            )

        return SimulationFormula(
            id=sim.id,
            name=sim.name,
            description=sim.description,
            inputs=inputs,
            calculations=sim.calculations,
            outputs=outputs,
            tags=sim.tags or [],
        )
