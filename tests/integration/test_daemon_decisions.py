"""Integration tests for the human-in-the-loop decisions route (Jalon 2-E).

A run parked on a ``confirm`` step is resumed by ``POST /v1/runs/{id}/decisions``. The token is read
back from the store's audit trail (which the daemon writes off the event stream), avoiding concurrent
WebSocket and HTTP traffic on the TestClient's single loop. Draining the WebSocket to ``done`` is the
deterministic "run finished" barrier — no sleeps on the run itself.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aetherius.config import settings as settings_mod
from aetherius.server import DaemonConfig, create_app
from aetherius.store import engine as engine_mod

pytestmark = pytest.mark.integration

# A network-free Blueprint: park on confirm, then a guarded step whose run proves the decision.
_CONFIRM_BP: dict[str, Any] = {
    "aetherius": "1.0",
    "name": "t.confirm.daemon",
    "act": "vector",
    "steps": [
        {
            "id": "approve",
            "action": "confirm",
            "message": "proceed?",
            "timeout_ms": 15000,
            "on_timeout": "fail:NO_DECISION",
        },
        {
            "id": "after",
            "when": "{{ steps.approve.approved }}",
            "action": "set",
            "value": "ran",
        },
    ],
    "outputs": {"approved": "{{ steps.approve.approved }}"},
}


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AETHERIUS_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()


def _await_pending_token(run_id: str, timeout_s: float = 5.0) -> str:
    """Poll the store's audit trail until the parked confirm is recorded, returning its token."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        rows = engine_mod.get_store().approvals.for_run(run_id)
        pending = [r for r in rows if r["status"] == "pending"]
        if pending:
            return str(pending[0]["token"])
        time.sleep(0.05)
    raise AssertionError(f"No pending approval recorded for run {run_id!r}")


def _drain(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with client.websocket_connect(f"/v1/runs/{run_id}/events") as ws:
        try:
            while True:
                events.append(ws.receive_json())
        except WebSocketDisconnect:
            pass
    return events


def test_decision_resumes_a_parked_run() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        run_id = client.post("/v1/runs", json={"blueprint": _CONFIRM_BP}).json()["run_id"]
        token = _await_pending_token(run_id)

        ack = client.post(f"/v1/runs/{run_id}/decisions", json={"token": token, "approved": True})
        assert ack.status_code == 200
        assert ack.json()["accepted"] is True

        events = _drain(client, run_id)
        assert [e["type"] for e in events][-1] == "done"
        assert "input_requested" in {e["type"] for e in events}
        assert "input_provided" in {e["type"] for e in events}

        run = client.get(f"/v1/runs/{run_id}").json()
    assert run["status"] == "succeeded"
    assert run["outputs"]["approved"] is True

    # The audit trail reflects the resolution.
    row = engine_mod.get_store().approvals.get(token)
    assert row is not None and row["status"] == "approved"


def test_rejection_skips_the_guarded_step() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        run_id = client.post("/v1/runs", json={"blueprint": _CONFIRM_BP}).json()["run_id"]
        token = _await_pending_token(run_id)
        client.post(f"/v1/runs/{run_id}/decisions", json={"token": token, "approved": False})
        _drain(client, run_id)
        run = client.get(f"/v1/runs/{run_id}").json()
    assert run["status"] == "succeeded"
    assert run["outputs"]["approved"] is False


def test_unknown_token_is_rejected_cleanly() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        run_id = client.post("/v1/runs", json={"blueprint": _CONFIRM_BP}).json()["run_id"]
        _await_pending_token(run_id)

        bad = client.post(f"/v1/runs/{run_id}/decisions", json={"token": "wrong", "approved": True})
        assert bad.status_code == 409

        # An unknown run is a 404, distinct from a bad token (409).
        assert (
            client.post(
                "/v1/runs/does-not-exist/decisions", json={"token": "x", "approved": True}
            ).status_code
            == 404
        )

        # Free the parked run so the test does not wait out the full timeout.
        token = _await_pending_token(run_id)
        client.post(f"/v1/runs/{run_id}/decisions", json={"token": token, "approved": False})
        _drain(client, run_id)
