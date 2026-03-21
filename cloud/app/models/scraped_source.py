"""Model for scraped/external data sources (spec: data scraped from the internet)."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ScrapedSource(Base):
    """Admin-configured URL or search query; scraped text is stored for context injection."""

    __tablename__ = "scraped_sources"

    id = Column(String(36), primary_key=True, default=_uuid)
    url_or_query = Column(String(2000), nullable=False)
    source_type = Column(String(50), nullable=False, default="url")  # "url" | "search_query"
    scraped_text = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # pending | completed | failed
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
