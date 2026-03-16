from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    knowledge_base_id = Column(String(36), ForeignKey("knowledge_bases.id"), nullable=False)

    filename = Column(String(300), nullable=False)
    content_type = Column(String(100), nullable=False)
    s3_path = Column(String(500), nullable=True)
    extracted_text = Column(String, nullable=True)
    optimized_text = Column(String, nullable=True)

    # "framework" | "simulation_program" | "simulation_description"
    document_type = Column(String(50), nullable=False, default="framework")

    # For simulation_description docs, links to the companion .py program
    companion_document_id = Column(String(36), ForeignKey("knowledge_documents.id"), nullable=True)

    upload_timestamp = Column(DateTime, default=datetime.utcnow)
