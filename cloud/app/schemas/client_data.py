from pydantic import BaseModel, Field, model_validator


class ClientDataCreate(BaseModel):
    label: str
    content: str = ""
    metadata: dict = Field(default_factory=dict)


class ClientDataOut(BaseModel):
    id: str
    client_id: str
    label: str
    content: str
    metadata: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _resolve_metadata(cls, data):
        """Read metadata_ (the ORM attribute) instead of metadata (which collides with SQLAlchemy's descriptor)."""
        if hasattr(data, "metadata_"):
            # ORM object: read the actual column attribute
            md = data.metadata_
            if not isinstance(md, dict):
                md = {}
            # Convert to dict for Pydantic
            return {
                "id": data.id,
                "client_id": data.client_id,
                "label": data.label,
                "content": data.content,
                "metadata": md,
            }
        return data
