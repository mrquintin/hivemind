from __future__ import annotations

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str
    license_key: str
    subscription_tier: str | None = None
    industry: str | None = None
    enabled_agent_ids: list[str] = Field(default_factory=list)
    app_version: str | None = None


class ClientOut(BaseModel):
    id: str
    name: str
    license_key: str
    subscription_tier: str | None = None
    industry: str | None = None
    enabled_agent_ids: list[str]
    app_version: str | None = None

    class Config:
        from_attributes = True
