"""Load and parse a Blueprint from a JSON or YAML file, validate it against the JSON Schema,
then return a typed Blueprint model."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from pydantic import ValidationError

from ..errors import BlueprintLoadError, BlueprintSchemaError
from .models import Blueprint

_schema: dict[str, Any] | None = None


def blueprint_schema() -> dict[str, Any]:
    """Return the packaged Blueprint JSON Schema (cached singleton)."""
    global _schema
    if _schema is None:
        pkg = importlib.resources.files("aetherius._contracts")
        schema_text = (pkg / "blueprint.schema.json").read_text(encoding="utf-8")
        _schema = json.loads(schema_text)
    return _schema


def _get_schema() -> dict[str, Any]:
    """Deprecated internal alias for blueprint_schema(); kept for existing callers."""
    return blueprint_schema()


def validate_blueprint_data(data: Any, *, source: str = "<data>") -> Blueprint:
    """Validate an in-memory Blueprint dict against the schema and model, returning the model.

    The counterpart to :func:`load_blueprint` for data that never touched disk (the builder assembles
    a Blueprint before there is a file). *source* only labels error messages.

    Raises:
        BlueprintSchemaError: JSON Schema violation or Pydantic constraint failure.
    """
    try:
        jsonschema.validate(data, blueprint_schema())
    except jsonschema.ValidationError as exc:
        raise BlueprintSchemaError(
            f"Blueprint schema violation in {source}: {exc.message}"
        ) from exc

    try:
        return Blueprint.model_validate(data)
    except ValidationError as exc:
        raise BlueprintSchemaError(f"Blueprint model validation failed in {source}: {exc}") from exc


def load_blueprint(path: str | Path) -> Blueprint:
    """Parse a Blueprint file (JSON or YAML) and return a validated model.

    Raises:
        BlueprintLoadError: file not found or not parseable.
        BlueprintSchemaError: JSON Schema violation or Pydantic constraint failure.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BlueprintLoadError(f"Blueprint file not found: {path}")
    except OSError as exc:
        raise BlueprintLoadError(f"Cannot read Blueprint file: {path} — {exc}") from exc

    suffix = path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            data: Any = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise BlueprintLoadError(f"Cannot parse Blueprint file: {path} — {exc}") from exc

    return validate_blueprint_data(data, source=str(path))
