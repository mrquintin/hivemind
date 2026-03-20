from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(String(36), primary_key=True, default=_uuid)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True)

    request = Column(JSONB, nullable=False)
    recommendations = Column(JSONB, nullable=False)
    vetoed_solutions = Column(JSONB, nullable=True)
    debate_rounds = Column(Integer, nullable=False, default=0)
    duration = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    audit_trail = Column(JSONB, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow)
