from __future__ import annotations

from pydantic import BaseModel


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str | None = None
    decision_types: list[str] = []


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    document_count: int
    chunk_count: int
    total_tokens: int
    embedding_model: str
    decision_types: list[str] = []

    class Config:
        from_attributes = True


class TestRetrievalRequest(BaseModel):
    query: str


class UploadTextRequest(BaseModel):
    title: str
    content: str
