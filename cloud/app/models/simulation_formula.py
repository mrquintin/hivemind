import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SimulationFormula(Base):
    """Simulation: formula (math expression) or python_program (sandboxed code with clear inputs/outputs)."""
    __tablename__ = "simulation_formulas"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)
    simulation_type = Column(String(50), nullable=False, default="formula")  # formula | python_program

    inputs = Column(JSONB, nullable=False, default=list)
    calculations = Column(Text, nullable=False)
    outputs = Column(JSONB, nullable=False, default=list)
    code = Column(Text, nullable=True)  # Python source when simulation_type == python_program
    tags = Column(JSONB, nullable=False, default=list)

    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
