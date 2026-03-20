from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SimulationIO(BaseModel):
    name: str
    description: str | None = None
    unit: str | None = None
    default_value: float | int | str | None = None


class SimulationFormulaCreate(BaseModel):
    name: str
    description: str | None = None
    simulation_type: str = Field(default="formula", pattern="^(formula|python_program)$")
    inputs: list[SimulationIO] = Field(default_factory=list)
    calculations: str = ""
    outputs: list[SimulationIO] = Field(default_factory=list)
    code: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None


class SimulationFormulaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    simulation_type: str | None = None
    inputs: list[SimulationIO] | None = None
    calculations: str | None = None
    outputs: list[SimulationIO] | None = None
    code: str | None = None
    tags: list[str] | None = None


class SimulationFormulaOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    simulation_type: str = "formula"
    inputs: list[SimulationIO]
    calculations: str
    outputs: list[SimulationIO]
    code: str | None = None
    tags: list[str]
    created_by: str | None = None

    @field_validator("simulation_type", mode="before")
    @classmethod
    def default_simulation_type(cls, v: str | None) -> str:
        return v or "formula"

    class Config:
        from_attributes = True


class SimulationRunRequest(BaseModel):
    inputs: dict[str, float | int | str] = Field(default_factory=dict)


class SimulationRunResponse(BaseModel):
    outputs: dict[str, float | int | str | None]
    variables: dict[str, float | int | str]
