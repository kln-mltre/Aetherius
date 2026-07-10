"""Endpoints to validate Blueprints and expose the JSON Schema."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ...core.blueprint.loader import blueprint_schema
from ...core.blueprint.models import Blueprint
from ...core.blueprint.validator import validate_for_act
from ...core.errors import BlueprintValidationError
from ..deps import require_auth
from ..schemas import ValidationErrorItem, ValidationReport

router = APIRouter(prefix="/v1", tags=["blueprints"], dependencies=[Depends(require_auth)])


@router.post("/blueprints/validate", response_model=ValidationReport)
async def validate_blueprint(body: dict[str, Any]) -> ValidationReport:
    """Validate a Blueprint against the schema and its Act's capabilities. Never raises: a malformed
    Blueprint yields ``valid: false`` with a per-error path/message report."""
    errors: list[ValidationErrorItem] = []

    validator = Draft202012Validator(blueprint_schema())
    for err in sorted(validator.iter_errors(body), key=lambda e: e.json_path):
        errors.append(ValidationErrorItem(path=err.json_path, message=err.message))

    if not errors:
        try:
            validate_for_act(Blueprint.model_validate(body))
        except BlueprintValidationError as exc:
            errors.append(ValidationErrorItem(path="$", message=str(exc)))
        except ValidationError as exc:
            errors.append(ValidationErrorItem(path="$", message=str(exc)))

    return ValidationReport(valid=not errors, errors=errors)


@router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the Blueprint JSON Schema (the structural source of truth)."""
    return blueprint_schema()
