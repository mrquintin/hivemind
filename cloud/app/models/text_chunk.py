import uuid

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TextChunk(Base):
    __tablename__ = "text_chunks"

    id = Column(String(36), primary_key=True, default=_uuid)
    document_id = Column(String(36), ForeignKey("knowledge_documents.id"), nullable=False)
    knowledge_base_id = Column(String(36), ForeignKey("knowledge_bases.id"), nullable=False)

    content = Column(String, nullable=False)
    embedding = Column(JSONB, nullable=True)
    token_count = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    source_page = Column(Integer, nullable=True)
