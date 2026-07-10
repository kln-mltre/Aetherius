"""End-to-end integration tests for the local daemon.

Exercised through Starlette's TestClient, which speaks real HTTP + WebSocket against the ASGI app.
The client is always context-managed (``with TestClient(...)``): that keeps a single, persistent
event loop across requests so the background run task is not torn down between calls. Draining the
WebSocket to its ``done`` event is the deterministic barrier for "the run has finished" — no sleeps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aetherius.server import DaemonConfig, create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def selftest_bp(examples_dir: Path) -> dict[str, Any]:
    text = (examples_dir / "vector" / "daemon-selftest.blueprint.json").read_text(encoding="utf-8")
    return json.loads(text)  # type: ignore[no-any-return]


def _drain_events(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    """Read the whole event stream until the daemon closes it (run finished)."""
    events: list[dict[str, Any]] = []
    with client.websocket_connect(f"/v1/runs/{run_id}/events") as ws:
        try:
            while True:
                events.append(ws.receive_json())
        except WebSocketDisconnect:
            pass
    return events


def test_health_is_unauthenticated_and_reports_version() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_schema_endpoint_returns_the_blueprint_schema() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        response = client.get("/v1/schema")

    assert response.status_code == 200
    assert response.json()["title"] == "Aetherius Blueprint"


def test_run_selftest_streams_events_and_returns_outputs(selftest_bp: dict[str, Any]) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        handle = client.post(
            "/v1/runs", json={"blueprint": selftest_bp, "inputs": {"subject": "daemon"}}
        )
        assert handle.status_code == 202
        run_id = handle.json()["run_id"]

        events = _drain_events(client, run_id)
        assert [event["type"] for event in events][-1] == "done"

        run = client.get(f"/v1/runs/{run_id}").json()
        assert run["status"] == "succeeded"
        assert run["outputs"]["greeting"] == "hello, daemon"
        assert run["error"] is None


def test_run_accepts_a_blueprint_path(examples_dir: Path) -> None:
    path = str(examples_dir / "vector" / "daemon-selftest.blueprint.json")
    with TestClient(create_app(DaemonConfig())) as client:
        run_id = client.post("/v1/runs", json={"blueprint": path}).json()["run_id"]
        _drain_events(client, run_id)

        assert client.get(f"/v1/runs/{run_id}").json()["status"] == "succeeded"


_VECTOR_PAYLOAD = [
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
        return httpx.Response(
            200, json=_VECTOR_PAYLOAD, headers={"Content-Type": "application/json"}
        )

    return httpx.MockTransport(handler)


def test_run_vector_example_over_the_daemon(examples_dir: Path) -> None:
    """A real network Blueprint (Act I) flows through the daemon, with the transport mocked."""
    blueprint = json.loads(
        (examples_dir / "vector" / "ukit-planning-week.blueprint.json").read_text(encoding="utf-8")
    )
    with TestClient(create_app(DaemonConfig())) as client:
        # Patch only around submit+drain: the run's VectorClient is built on the worker thread while
        # the stream is being consumed, so the mock must be active for that whole window.
        with patch("httpx.Client", return_value=httpx.Client(transport=_mock_transport())):
            run_id = client.post(
                "/v1/runs",
                json={
                    "blueprint": blueprint,
                    "inputs": {"group": "TP-A1", "monday": "2026-09-07"},
                },
            ).json()["run_id"]
            _drain_events(client, run_id)

        run = client.get(f"/v1/runs/{run_id}").json()

    assert run["status"] == "succeeded"
    assert "events" in run["outputs"]


def test_unknown_run_returns_404() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        assert client.get("/v1/runs/nope").status_code == 404


def test_streaming_an_unknown_run_closes_the_socket() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        with client.websocket_connect("/v1/runs/nope/events") as ws:
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_validate_endpoint_reports_schema_errors() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        bad = client.post("/v1/blueprints/validate", json={"name": "x"})
        assert bad.status_code == 200
        report = bad.json()
        assert report["valid"] is False
        assert report["errors"]


def test_validate_endpoint_accepts_a_good_blueprint(selftest_bp: dict[str, Any]) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        report = client.post("/v1/blueprints/validate", json=selftest_bp).json()

    assert report["valid"] is True
    assert report["errors"] == []


def test_recorder_endpoint_is_deferred() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        response = client.post("/v1/recorder/sessions")

    assert response.status_code == 501
    assert "aetherius record" in response.json()["detail"]


def test_token_gates_the_v1_surface_but_not_health() -> None:
    with TestClient(create_app(DaemonConfig(token="s3cr3t"))) as client:
        assert client.get("/v1/schema").status_code == 401
        assert client.get("/health").status_code == 200
        authorized = client.get("/v1/schema", headers={"Authorization": "Bearer s3cr3t"})
        assert authorized.status_code == 200
