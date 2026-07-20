"""Tests for server/jobs.py — the async RunManager and its thread-safe event sink.

Driven directly under a real asyncio loop (not the TestClient), which is where the manager's
create_task + to_thread lifecycle is exercised faithfully.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aetherius.core.blueprint.loader import load_blueprint
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.approvals import Decision
from aetherius.server.jobs import QueueSink, RunManager

pytestmark = pytest.mark.unit

_CONFIRM_BP = {
    "aetherius": "1.0",
    "name": "t.confirm.jobs",
    "act": "vector",
    "steps": [
        {"id": "approve", "action": "confirm", "message": "ok?", "timeout_ms": 8000},
        {"id": "after", "when": "{{ steps.approve.approved }}", "action": "set", "value": "ran"},
    ],
    "outputs": {"approved": "{{ steps.approve.approved }}"},
}


@pytest.fixture
def selftest(examples_dir: Path) -> Blueprint:
    return load_blueprint(str(examples_dir / "vector" / "daemon-selftest.blueprint.json"))


async def _run_to_completion(manager: RunManager, blueprint: Blueprint, **kwargs: object) -> str:
    run_id = await manager.submit(blueprint, kwargs.get("inputs"), kwargs.get("secrets"))  # type: ignore[arg-type]
    job = manager.get(run_id)
    assert job is not None
    await asyncio.wait_for(job.finished.wait(), timeout=5)
    return run_id


async def test_submit_runs_to_completion(selftest: Blueprint) -> None:
    manager = RunManager()
    run_id = await manager.submit(selftest, {"subject": "jobs"}, {})
    job = manager.get(run_id)
    assert job is not None

    await asyncio.wait_for(job.finished.wait(), timeout=5)

    assert job.status == "succeeded"
    assert job.result is not None
    assert job.result.outputs["greeting"] == "hello, jobs"
    assert job.error is None


async def test_history_ends_with_done(selftest: Blueprint) -> None:
    manager = RunManager()
    run_id = await _run_to_completion(manager, selftest)
    job = manager.get(run_id)
    assert job is not None

    types = [event.type.value for event in job.history]
    assert types[0] == "progress"
    assert types[-1] == "done"


async def test_subscribe_replays_a_finished_run(selftest: Blueprint) -> None:
    manager = RunManager()
    run_id = await _run_to_completion(manager, selftest)

    queue = manager.subscribe(run_id)
    assert queue is not None

    received: list[RunEvent] = []
    while True:
        event = await queue.get()
        if event is None:  # sentinel closes the replay
            break
        received.append(event)

    assert [event.type.value for event in received][-1] == "done"


async def test_subscribe_unknown_run_returns_none() -> None:
    assert RunManager().subscribe("does-not-exist") is None


async def _await_token(manager: RunManager, run_id: str, timeout: float = 5.0) -> str:
    """Yield to the loop until the run's confirm parks (the input_requested event is ingested)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        job = manager.get(run_id)
        assert job is not None
        for event in job.history:
            if event.type is EventType.INPUT_REQUESTED:
                return str(event.data["token"])
        await asyncio.sleep(0.02)
    raise AssertionError("run never parked on a confirm")


async def test_resolve_decision_resumes_a_parked_run() -> None:
    manager = RunManager()
    run_id = await manager.submit(Blueprint.model_validate(_CONFIRM_BP), None, None)
    token = await _await_token(manager, run_id)

    assert manager.resolve_decision(run_id, token, Decision(True, decided_by="test")) is True

    job = manager.get(run_id)
    assert job is not None
    await asyncio.wait_for(job.finished.wait(), timeout=5)
    assert job.status == "succeeded"
    assert job.result is not None
    assert job.result.outputs["approved"] is True


async def test_resolve_decision_unknown_run_is_false() -> None:
    assert RunManager().resolve_decision("does-not-exist", "tok", Decision(True)) is False


def test_queue_sink_never_raises_on_a_closed_loop() -> None:
    loop = asyncio.new_event_loop()
    loop.close()
    sink = QueueSink(loop, lambda event: None)

    # A closed loop makes call_soon_threadsafe raise; the sink must swallow it (never abort a run).
    sink.on_event(RunEvent(run_id="x", type=EventType.PROGRESS))
