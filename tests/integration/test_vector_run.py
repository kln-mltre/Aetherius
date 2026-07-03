"""End-to-end integration test for Act I (Vector).

Runs the ukit-planning-week example Blueprint against a MockTransport that simulates
the ADE API, without any real network I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

import aetherius
from aetherius.core.runtime.result import Result, RunStatus

pytestmark = pytest.mark.integration

_API_PAYLOAD = [
    {
        "id": "ev-1",
        "start": "2026-09-07T08:00:00",
        "end": "2026-09-07T10:00:00",
        "eventCategory": "Cours",
        "backgroundColor": "#3b82f6",
        "description": "Mathématiques",
    },
    {
        "id": "ev-2",
        "start": "2026-09-07T12:00:00",
        "end": "2026-09-07T14:00:00",
        "eventCategory": "Vacances",
        "backgroundColor": "#f00",
        "description": "Jour férié",
    },
    {
        "id": "ev-3",
        "start": "2026-09-07T14:00:00",
        "end": "2026-09-07T16:00:00",
        "eventCategory": "TD",
        "backgroundColor": "#10b981",
        "description": "Travaux dirigés",
    },
]


def _make_transport(payload: list[Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, headers={"Content-Type": "application/json"})

    return httpx.MockTransport(handler)


@pytest.fixture
def ukit_blueprint(examples_dir: Path) -> Path:
    return examples_dir / "ukit-planning-week.blueprint.json"


def test_ukit_run_success(ukit_blueprint: Path) -> None:
    transport = _make_transport(_API_PAYLOAD)

    # Patch httpx.Client at the source so VectorClient uses our mock transport.
    with patch("httpx.Client", return_value=httpx.Client(transport=transport)):
        result = aetherius.Aetherius().run(
            str(ukit_blueprint),
            inputs={"group": "TP-A1", "monday": "2026-09-07"},
        )

    assert isinstance(result, Result)
    assert result.status == RunStatus.SUCCESS
    assert result.error is None
    assert "events" in result.outputs


def test_ukit_run_filters_vacances(ukit_blueprint: Path) -> None:
    transport = _make_transport(_API_PAYLOAD)

    with patch("httpx.Client", return_value=httpx.Client(transport=transport)):
        result = aetherius.Aetherius().run(
            str(ukit_blueprint),
            inputs={"group": "TP-A1", "monday": "2026-09-07"},
        )

    events = result.outputs["events"]
    categories = [e.get("category") for e in events]
    assert "Vacances" not in categories
    assert len(events) == 2


def test_ukit_run_fields_mapping(ukit_blueprint: Path) -> None:
    transport = _make_transport(_API_PAYLOAD)

    with patch("httpx.Client", return_value=httpx.Client(transport=transport)):
        result = aetherius.Aetherius().run(
            str(ukit_blueprint),
            inputs={"group": "TP-A1", "monday": "2026-09-07"},
        )

    events = result.outputs["events"]
    assert len(events) > 0
    first = events[0]
    # The example Blueprint maps: id, start, end, category, color, description
    assert "id" in first
    assert "start" in first
    assert "category" in first


def test_missing_required_input_raises(ukit_blueprint: Path) -> None:
    from aetherius.core.errors import BlueprintValidationError

    with pytest.raises(BlueprintValidationError, match="group|monday"):
        aetherius.Aetherius().run(str(ukit_blueprint), inputs={})


def test_run_with_wrong_path_raises() -> None:
    from aetherius.core.errors import BlueprintLoadError

    with pytest.raises(BlueprintLoadError):
        aetherius.Aetherius().run("/nonexistent/file.json")
