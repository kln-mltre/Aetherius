"""End-to-end integration tests for the daemon's schedule surface (Jalon D).

Same harness as test_daemon_run.py: Starlette's TestClient over the real ASGI app, with the store
isolated on a temporary file. Opening the client runs the lifespan, so the real SchedulerService
tick loop is alive during every test.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aetherius.config import settings as settings_mod
from aetherius.server import DaemonConfig, create_app
from aetherius.store import ScheduleRecord
from aetherius.store import engine as engine_mod

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AETHERIUS_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()


@pytest.fixture
def selftest_path(examples_dir: Path) -> str:
    return str(examples_dir / "vector" / "daemon-selftest.blueprint.json")


def _payload(selftest_path: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "watch",
        "blueprint": selftest_path,
        "inputs": {"subject": "scheduled"},
        "trigger": {"kind": "interval", "seconds": 3600},
    }
    payload.update(overrides)
    return payload


def _drain_events(client: TestClient, run_id: str) -> None:
    with client.websocket_connect(f"/v1/runs/{run_id}/events") as ws:
        try:
            while True:
                ws.receive_json()
        except WebSocketDisconnect:
            pass


def test_schedule_crud_roundtrip(selftest_path: str) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        created = client.post("/v1/schedules", json=_payload(selftest_path))
        assert created.status_code == 201
        schedule = created.json()
        assert schedule["next_run_at"] is not None
        schedule_id = schedule["id"]

        assert client.get("/v1/schedules").json()[0]["id"] == schedule_id
        assert client.get(f"/v1/schedules/{schedule_id}").json()["name"] == "watch"

        paused = client.patch(f"/v1/schedules/{schedule_id}", json={"enabled": False})
        assert paused.json()["enabled"] is False

        resumed = client.patch(f"/v1/schedules/{schedule_id}", json={"enabled": True})
        assert resumed.json()["enabled"] is True
        assert resumed.json()["next_run_at"] >= datetime.now(timezone.utc).isoformat()[:19]

        assert client.delete(f"/v1/schedules/{schedule_id}").status_code == 204
        assert client.get(f"/v1/schedules/{schedule_id}").status_code == 404


def test_create_rejects_a_bad_trigger_and_policy(selftest_path: str) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        bad_trigger = client.post(
            "/v1/schedules", json=_payload(selftest_path, trigger={"kind": "cron", "expr": "nope"})
        )
        bad_notify = client.post(
            "/v1/schedules", json=_payload(selftest_path, notify={"channel": "pigeon"})
        )

    assert bad_trigger.status_code == 422
    assert bad_notify.status_code == 422


def test_patching_the_trigger_recomputes_the_next_fire(selftest_path: str) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        schedule = client.post("/v1/schedules", json=_payload(selftest_path)).json()

        updated = client.patch(
            f"/v1/schedules/{schedule['id']}",
            json={"trigger": {"kind": "interval", "seconds": 60}},
        )

        assert updated.status_code == 200
        assert updated.json()["trigger"] == {"kind": "interval", "seconds": 60}
        assert updated.json()["next_run_at"] != schedule["next_run_at"]


def test_manual_fire_runs_like_any_other_run(selftest_path: str) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        schedule = client.post("/v1/schedules", json=_payload(selftest_path)).json()

        fired = client.post(f"/v1/schedules/{schedule['id']}/run")
        assert fired.status_code == 202
        run_id = fired.json()["run_id"]
        _drain_events(client, run_id)

        run = client.get(f"/v1/runs/{run_id}").json()
        assert run["status"] == "succeeded"
        assert run["outputs"]["greeting"] == "hello, scheduled"

        # The cadence is untouched, but the history carries the schedule link.
        assert client.get(f"/v1/schedules/{schedule['id']}").json()["last_run_at"] is None

    persisted = engine_mod.get_store().runs.get(run_id)
    assert persisted is not None
    assert persisted.schedule_id == schedule["id"]


def test_manual_fire_surfaces_a_broken_blueprint(selftest_path: str) -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        schedule = client.post(
            "/v1/schedules", json=_payload(selftest_path, blueprint="/vanished.json")
        ).json()

        fired = client.post(f"/v1/schedules/{schedule['id']}/run")

    assert fired.status_code == 422


def test_unknown_schedule_answers_404() -> None:
    with TestClient(create_app(DaemonConfig())) as client:
        assert client.get("/v1/schedules/nope").status_code == 404
        assert client.patch("/v1/schedules/nope", json={}).status_code == 404
        assert client.delete("/v1/schedules/nope").status_code == 404
        assert client.post("/v1/schedules/nope/run").status_code == 404


def test_token_gates_the_schedule_surface() -> None:
    with TestClient(create_app(DaemonConfig(token="s3cr3t"))) as client:
        assert client.get("/v1/schedules").status_code == 401
        authorized = client.get("/v1/schedules", headers={"Authorization": "Bearer s3cr3t"})
        assert authorized.status_code == 200


def test_the_tick_loop_fires_a_due_schedule_and_persists_the_run(selftest_path: str) -> None:
    """A schedule already due when the daemon starts is fired by the real tick loop."""
    store = engine_mod.get_store()
    record = ScheduleRecord(
        id="sch-live",
        name="live",
        blueprint=selftest_path,
        inputs={"subject": "loop"},
        trigger={"kind": "interval", "seconds": 3600},
        created_at=datetime.now(timezone.utc),
        next_run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    store.schedules.create(record)

    with TestClient(create_app(DaemonConfig(scheduler_tick_seconds=0.05))) as client:
        assert client.get("/health").status_code == 200
        deadline = time.monotonic() + 10
        runs = store.runs.recent(schedule_id="sch-live")
        while not runs and time.monotonic() < deadline:
            time.sleep(0.05)
            runs = store.runs.recent(schedule_id="sch-live")

    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].outputs["greeting"] == "hello, loop"

    updated = store.schedules.get("sch-live")
    assert updated is not None
    assert updated.next_run_at is not None
    assert updated.next_run_at > datetime.now(timezone.utc)
