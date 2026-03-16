from pydantic import BaseModel, Field


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
