"""Tests for core/blueprint/loader.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.core.blueprint.loader import load_blueprint
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import BlueprintLoadError, BlueprintSchemaError

pytestmark = pytest.mark.unit


@pytest.fixture
def minimal_json(tmp_path: Path) -> Path:
    data = {
        "aetherius": "1.0",
        "name": "test.load",
        "act": "vector",
        "steps": [{"action": "http.request", "url": "https://example.com"}],
    }
    p = tmp_path / "test.blueprint.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def minimal_yaml(tmp_path: Path) -> Path:
    content = """\
aetherius: "1.0"
name: test.load.yaml
act: vector
steps:
  - action: http.request
    url: https://example.com
"""
    p = tmp_path / "test.blueprint.yaml"
    p.write_text(content)
    return p


def test_load_json(minimal_json: Path) -> None:
    bp = load_blueprint(minimal_json)
    assert isinstance(bp, Blueprint)
    assert bp.name == "test.load"


def test_load_yaml(minimal_yaml: Path) -> None:
    bp = load_blueprint(minimal_yaml)
    assert bp.name == "test.load.yaml"


def test_load_missing_file_raises() -> None:
    with pytest.raises(BlueprintLoadError, match="not found"):
        load_blueprint("/nonexistent/path/blueprint.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(BlueprintLoadError, match="Cannot parse"):
        load_blueprint(p)


def test_load_schema_violation_raises(tmp_path: Path) -> None:
    data = {"aetherius": "1.0", "name": "x"}  # missing 'act' and 'steps'
    p = tmp_path / "bad_schema.json"
    p.write_text(json.dumps(data))
    with pytest.raises(BlueprintSchemaError):
        load_blueprint(p)


def test_load_examples_conform(examples_dir: Path) -> None:
    """All example Blueprints must load without error."""
    for path in examples_dir.glob("*.blueprint.json"):
        bp = load_blueprint(path)
        assert isinstance(bp, Blueprint)
