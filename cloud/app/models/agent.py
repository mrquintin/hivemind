import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    network_type = Column(String(50), nullable=False)  # theory | practicality
    description = Column(String(1000), nullable=True)

    framework = Column(String(500), nullable=True)
    principles = Column(String(2000), nullable=True)
    analytical_style = Column(String(500), nullable=True)

    scoring_criteria = Column(String(2000), nullable=True)
    score_interpretation = Column(String(2000), nullable=True)

    knowledge_base_ids = Column(JSONB, nullable=False, default=list)
    rag_config = Column(JSONB, nullable=False, default=dict)
    simulation_formula_ids = Column(JSONB, nullable=False, default=list)

    status = Column(String(50), nullable=False, default="draft")
    use_case_profile = Column(String(100), nullable=True)  # e.g. small_business, individual_career
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(String(200), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
