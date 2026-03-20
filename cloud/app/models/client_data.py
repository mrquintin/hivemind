from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ClientData(Base):
    __tablename__ = "client_data"

    id = Column(String(36), primary_key=True, default=_uuid)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    label = Column(String(300), nullable=False)
    content = Column(Text, nullable=False, default="")
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
