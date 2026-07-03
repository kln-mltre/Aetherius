"""Tests for cli.py — the typer application, using CliRunner (no real network I/O)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from aetherius.cli import app, main

pytestmark = pytest.mark.unit

runner = CliRunner()

_API_PAYLOAD = [
    {
        "id": "ev-1",
        "start": "2026-09-07T08:00:00",
        "end": "2026-09-07T10:00:00",
        "eventCategory": "Cours",
        "backgroundColor": "#3b82f6",
        "description": "Mathématiques",
    }
]


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_API_PAYLOAD, headers={"Content-Type": "application/json"})

    return httpx.MockTransport(handler)


def test_validate_accepts_a_well_formed_vector_blueprint(examples_dir: Path) -> None:
    result = runner.invoke(
        app, ["validate", str(examples_dir / "ukit-planning-week.blueprint.json")]
    )

    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_validate_accepts_a_well_formed_oracle_blueprint(examples_dir: Path) -> None:
    # act=oracle is structurally valid even though it is not runnable yet.
    result = runner.invoke(app, ["validate", str(examples_dir / "tiktok-upload.blueprint.json")])

    assert result.exit_code == 0


def test_validate_rejects_a_nonexistent_file() -> None:
    result = runner.invoke(app, ["validate", "/nonexistent/file.json"])

    assert result.exit_code == 1


def test_run_executes_a_vector_blueprint_with_mocked_transport(examples_dir: Path) -> None:
    blueprint = examples_dir / "ukit-planning-week.blueprint.json"

    with patch("httpx.Client", return_value=httpx.Client(transport=_mock_transport())):
        result = runner.invoke(
            app,
            [
                "run",
                str(blueprint),
                "--input",
                "group=TP-A1",
                "--input",
                "monday=2026-09-07",
            ],
        )

    assert result.exit_code == 0
    assert "success" in result.stdout


def test_run_rejects_malformed_input_pair(examples_dir: Path) -> None:
    blueprint = examples_dir / "ukit-planning-week.blueprint.json"

    result = runner.invoke(app, ["run", str(blueprint), "--input", "no-equals-sign"])

    assert result.exit_code != 0


def test_run_reports_unimplemented_act_cleanly(examples_dir: Path) -> None:
    blueprint = examples_dir / "ukit-scolarite-login.blueprint.json"  # act=continuum

    result = runner.invoke(app, ["run", str(blueprint)])

    assert result.exit_code == 1
    assert "Error" in result.stdout
    assert "Traceback" not in result.stdout


def test_serve_reports_not_implemented() -> None:
    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 1
    assert "not implemented" in result.stdout


def test_record_reports_not_implemented() -> None:
    result = runner.invoke(app, ["record"])

    assert result.exit_code == 1
    assert "not implemented" in result.stdout


def test_bare_invocation_opens_the_console() -> None:
    with patch("aetherius.console.app.AetheriusConsoleApp.run") as mock_run:
        rc = main([])

    mock_run.assert_called_once()
    assert rc == 0
