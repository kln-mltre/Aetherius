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


def _get_schema() -> dict[str, Any]:
    global _schema
    if _schema is None:
        pkg = importlib.resources.files("aetherius._contracts")
        schema_text = (pkg / "blueprint.schema.json").read_text(encoding="utf-8")
        _schema = json.loads(schema_text)
    return _schema


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

    try:
        jsonschema.validate(data, _get_schema())
    except jsonschema.ValidationError as exc:
        raise BlueprintSchemaError(f"Blueprint schema violation in {path}: {exc.message}") from exc

    try:
        return Blueprint.model_validate(data)
    except ValidationError as exc:
        raise BlueprintSchemaError(f"Blueprint model validation failed in {path}: {exc}") from exc
