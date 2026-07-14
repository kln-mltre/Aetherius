"""The daemon OpenAPI contract is well-formed. A light structural check now; the server
implementation in src/aetherius/server is expected to conform to it as it is built."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contracts


def test_openapi_is_wellformed(contracts_dir: Path) -> None:
    spec = yaml.safe_load((contracts_dir / "openapi.yaml").read_text(encoding="utf-8"))

    assert isinstance(spec, dict)
    assert str(spec.get("openapi", "")).startswith("3."), spec.get("openapi")

    info = spec.get("info", {})
    assert info.get("title"), "openapi.info.title is required"
    assert info.get("version"), "openapi.info.version is required"

    paths = spec.get("paths")
    assert isinstance(paths, dict) and paths, "openapi.paths must be a non-empty mapping"


def test_openapi_declares_the_implemented_paths(contracts_dir: Path) -> None:
    spec = yaml.safe_load((contracts_dir / "openapi.yaml").read_text(encoding="utf-8"))
    paths = spec["paths"]

    for path in (
        "/health",
        "/v1/runs",
        "/v1/runs/{runId}",
        "/v1/runs/{runId}/events",
        "/v1/blueprints/validate",
        "/v1/schema",
        "/v1/schedules",
        "/v1/schedules/{scheduleId}",
        "/v1/schedules/{scheduleId}/run",
        "/v1/recorder/sessions",
    ):
        assert path in paths, f"{path} missing from the OpenAPI contract"
