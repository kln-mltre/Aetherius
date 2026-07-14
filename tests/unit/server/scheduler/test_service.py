"""Tests for scheduler/service.py — the tick loop, driven with a fake RunManager.

The fake completes every submitted run instantly, so ticks are deterministic: no sleeps except in
the start/stop lifecycle test, which exercises the real loop task at a tiny tick period.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.runtime.result import RunStatus
from aetherius.server.jobs import Job
from aetherius.server.scheduler import SchedulerService
from aetherius.server.scheduler import service as service_mod
from aetherius.store import Store

from .conftest import make_schedule

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeManager:
    """RunManager stand-in: records submissions and completes each run immediately."""

    status: RunStatus = RunStatus.SUCCESS
    outputs: dict[str, Any] = field(default_factory=dict)
    submissions: list[Any] = field(default_factory=list)
    jobs: dict[str, Job] = field(default_factory=dict)

    async def submit(
        self,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None,
        secrets: Mapping[str, str] | None,
        *,
        schedule_id: str | None = None,
    ) -> str:
        run_id = f"run-{len(self.submissions)}"
        self.submissions.append(
            SimpleNamespace(
                blueprint=blueprint.name,
                inputs=dict(inputs or {}),
                secrets=dict(secrets or {}),
                schedule_id=schedule_id,
            )
        )
        job = Job(run_id=run_id, schedule_id=schedule_id)
        job.status = "succeeded"
        job.result = SimpleNamespace(status=self.status, outputs=dict(self.outputs))  # type: ignore[assignment]
        job.finished.set()
        self.jobs[run_id] = job
        return run_id

    def get(self, run_id: str) -> Job | None:
        return self.jobs.get(run_id)


@pytest.fixture
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture
def service(manager: FakeManager, store: Store) -> SchedulerService:
    # tick_seconds=30 -> grace window of 60s, the documented default shape.
    return SchedulerService(manager, store, tick_seconds=30.0)


def _stored(store: Store, examples_dir: Path, **overrides: Any) -> str:
    """Insert a schedule due 10s ago (within grace) on the selftest Blueprint; return its id."""
    defaults: dict[str, Any] = {
        "blueprint": str(examples_dir / "vector" / "daemon-selftest.blueprint.json"),
        "next_run_at": _NOW - timedelta(seconds=10),
    }
    defaults.update(overrides)
    record = make_schedule(**defaults)
    store.schedules.create(record)
    return record.id


async def test_tick_fires_a_due_schedule_once(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    schedule_id = _stored(store, examples_dir, inputs={"subject": "tick"})

    await service.tick(_NOW)

    assert len(manager.submissions) == 1
    submission = manager.submissions[0]
    assert submission.schedule_id == schedule_id
    assert submission.inputs == {"subject": "tick"}

    updated = store.schedules.get(schedule_id)
    assert updated is not None
    assert updated.next_run_at is not None and updated.next_run_at > _NOW
    assert updated.last_run_at is not None


async def test_an_overlapping_tick_never_replays_the_same_slot(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    _stored(store, examples_dir)

    await service.tick(_NOW)
    await service.tick(_NOW)

    assert len(manager.submissions) == 1


async def test_a_disabled_schedule_is_ignored(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    _stored(store, examples_dir, enabled=False)

    await service.tick(_NOW)

    assert manager.submissions == []


async def test_skip_policy_reschedules_an_old_misfire_without_firing(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    schedule_id = _stored(
        store,
        examples_dir,
        trigger={"kind": "interval", "seconds": 60, "misfire": "skip"},
        next_run_at=_NOW - timedelta(hours=1),  # far beyond the 60s grace
    )

    await service.tick(_NOW)

    assert manager.submissions == []
    updated = store.schedules.get(schedule_id)
    assert updated is not None
    assert updated.next_run_at is not None and updated.next_run_at > _NOW
    assert updated.last_run_at is None  # nothing fired, so no fire is stamped


async def test_run_once_policy_coalesces_an_old_misfire_into_one_fire(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    _stored(store, examples_dir, next_run_at=_NOW - timedelta(hours=1))

    await service.tick(_NOW)

    assert len(manager.submissions) == 1


async def test_run_all_policy_replays_each_missed_slot(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    _stored(
        store,
        examples_dir,
        trigger={"kind": "interval", "seconds": 60, "misfire": "run_all"},
        next_run_at=_NOW - timedelta(minutes=3, seconds=30),
    )

    await service.tick(_NOW)

    assert len(manager.submissions) == 4


async def test_an_exhausted_at_schedule_stops_recurring(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    schedule_id = _stored(
        store,
        examples_dir,
        trigger={"kind": "at", "when": (_NOW - timedelta(seconds=10)).isoformat()},
    )

    await service.tick(_NOW)

    assert len(manager.submissions) == 1
    updated = store.schedules.get(schedule_id)
    assert updated is not None and updated.next_run_at is None
    assert store.schedules.due(_NOW + timedelta(days=1)) == []


async def test_a_missing_blueprint_lands_in_history_as_a_failed_run(
    service: SchedulerService, manager: FakeManager, store: Store
) -> None:
    schedule_id = "sch-1"
    store.schedules.create(
        make_schedule(
            blueprint="/nonexistent/blueprint.json", next_run_at=_NOW - timedelta(seconds=10)
        )
    )

    await service.tick(_NOW)

    assert manager.submissions == []
    runs = store.runs.recent(schedule_id=schedule_id)
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error


async def test_a_corrupt_trigger_disables_the_schedule(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    schedule_id = _stored(store, examples_dir, trigger={"kind": "bogus"})

    await service.tick(_NOW)

    assert manager.submissions == []
    updated = store.schedules.get(schedule_id)
    assert updated is not None and updated.enabled is False


async def test_fire_now_submits_without_touching_the_cadence(
    service: SchedulerService, manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    upcoming = _NOW + timedelta(hours=6)
    schedule_id = _stored(store, examples_dir, next_run_at=upcoming)
    record = store.schedules.get(schedule_id)
    assert record is not None

    run_id = await service.fire_now(record)

    assert run_id == "run-0"
    assert manager.submissions[0].schedule_id == schedule_id
    updated = store.schedules.get(schedule_id)
    assert updated is not None
    assert updated.next_run_at == upcoming
    assert updated.last_run_at is None


async def test_the_follower_applies_the_notify_policy(
    service: SchedulerService,
    manager: FakeManager,
    store: Store,
    examples_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[dict[str, Any]] = []

    def fake_apply(record: Any, **kwargs: Any) -> bool:
        applied.append({"schedule_id": record.id, **kwargs})
        return True

    monkeypatch.setattr(service_mod, "apply_notify_policy", fake_apply)
    manager.outputs = {"quote": "x"}
    schedule_id = _stored(store, examples_dir, notify={"channel": "webhook", "on": "always"})

    await service.tick(_NOW)
    await service.stop()  # gathers the follower tasks

    assert len(applied) == 1
    assert applied[0]["schedule_id"] == schedule_id
    assert applied[0]["status"] == "success"
    assert applied[0]["outputs"] == {"quote": "x"}


async def test_start_and_stop_drive_the_real_loop(
    manager: FakeManager, store: Store, examples_dir: Path
) -> None:
    service = SchedulerService(manager, store, tick_seconds=0.02)
    record = make_schedule(
        blueprint=str(examples_dir / "vector" / "daemon-selftest.blueprint.json"),
        next_run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    store.schedules.create(record)

    await service.start()
    try:
        for _ in range(100):  # deterministic barrier: poll until the loop's first tick fired
            if manager.submissions:
                break
            await asyncio.sleep(0.02)
    finally:
        await service.stop()

    assert len(manager.submissions) == 1
    assert service._task is None
