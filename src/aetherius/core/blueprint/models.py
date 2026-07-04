"""Pydantic v2 models for a Blueprint. Single typed representation of an instruction file.

Source of truth for the shape: contracts/blueprint.schema.json.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "number", "integer", "boolean", "date", "path", "object", "array"]
    required: bool = False
    format: str | None = None
    default: Any = None
    description: str | None = None


class RetriesOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max: int = 0
    backoff: Literal["none", "linear", "exponential"] = "none"


class SessionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str | None = None
    persist: bool = False


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    debug: bool = False
    timeout_ms: int | None = None
    retries: RetriesOptions = Field(default_factory=RetriesOptions)
    stealth: Any = None
    session: SessionOptions | None = None


class StepModel(BaseModel):
    # extra="allow": action-specific keys are passed through and validated per-action by the engine.
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    action: str

    @property
    def extra_fields(self) -> dict[str, Any]:
        """Action-specific parameters (all keys beyond id and action)."""
        return self.model_extra or {}


class Blueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aetherius: str
    name: str
    description: str | None = None
    act: Literal["vector", "continuum", "oracle", "phantom"]
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    secrets: list[str] = Field(default_factory=list)
    vars: dict[str, Any] = Field(default_factory=dict)
    options: Options = Field(default_factory=Options)
    vision: dict[str, Any] | None = None
    goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    steps: list[StepModel] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_steps_or_goal(self) -> "Blueprint":
        if not self.steps and not self.goal:
            raise ValueError("A Blueprint must declare either 'steps' or 'goal'.")
        return self
