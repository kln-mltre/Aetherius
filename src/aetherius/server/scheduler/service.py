"""SchedulerService: the async tick loop that fires due schedules through the RunManager.

Started and stopped from the FastAPI ``lifespan`` (see server/app.py). Each tick asks the store for
due schedules and submits them via ``RunManager.submit`` — reusing the daemon's existing
worker-thread + event-stream machinery, so a scheduled run behaves exactly like a manually
submitted one (same events, same durable history, plus the ``schedule_id`` link).

Single-loop discipline (same as server/jobs.py): the tick orchestrates on the asyncio loop; store
access and the engine stay on worker threads via ``asyncio.to_thread``. Idempotence: a schedule's
``next_run_at`` is advanced *before* its runs are submitted, so an overlapping or repeated tick can
never replay the same slot. Misfires (fire times missed while the daemon was down) are resolved by
the tick itself: anything overdue beyond a grace window goes through the schedule's misfire policy,
so the first tick after a restart catches up naturally — no dedicated startup phase.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Mapping

from ...config.secrets import resolve_secrets
from ...core.blueprint.loader import load_blueprint
from ...core.blueprint.models import Blueprint
from ...core.errors import AetheriusError
from ...store import RunRecord
from ...store.models import ScheduleRecord
from .alerts import apply_notify_policy
from .misfire import misfire_policy, resolve_misfires
from .triggers import next_run_at, parse_trigger

if TYPE_CHECKING:
    from ...store import Store
    from ..jobs import RunManager

_log = logging.getLogger("aetherius.scheduler")


class SchedulerService:
    """Owns the scheduler tick loop for the daemon's lifetime."""

    def __init__(
        self,
        manager: "RunManager",
        store: "Store",
        *,
        tick_seconds: float = 30.0,
    ) -> None:
        self._manager = manager
        self._store = store
        self._tick_seconds = tick_seconds
        # Overdue by more than this and the misfire policy decides; within it, it is a normal fire
        # (the daemon can never wake exactly on the slot — the tick period is the resolution).
        self._grace = timedelta(seconds=2 * tick_seconds)
        self._task: asyncio.Task[None] | None = None
        # Strong references to per-run follow-up tasks (the loop only keeps weak ones).
        self._followers: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Begin the background tick loop (called from the daemon's lifespan startup)."""
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="aetherius-scheduler")

    async def stop(self) -> None:
        """Stop the tick loop and let in-flight runs settle (lifespan shutdown).

        Followers are awaited, not cancelled: an alert for a run that already fired must still go
        out, and the RunManager keeps executing its jobs while the loop is alive.
        """
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._followers:
            await asyncio.gather(*self._followers, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick(datetime.now(timezone.utc))
            except Exception:  # noqa: BLE001 - one bad tick must not kill the scheduler
                _log.exception("Scheduler tick failed; continuing.")
            await asyncio.sleep(self._tick_seconds)

    async def tick(self, now: datetime) -> None:
        """Fire every schedule due at *now*. Driven by the loop; exposed for tests."""
        due = await asyncio.to_thread(self._store.schedules.due, now)
        for record in due:
            await self._fire_due(record, now)

    async def fire_now(self, record: ScheduleRecord) -> str:
        """Fire *record* immediately (manual trigger), leaving its cadence untouched.

        Returns the run id. Raises the underlying ``AetheriusError`` (missing Blueprint file,
        malformed Blueprint) so the API can surface it, unlike tick-driven fires which contain it.
        """
        blueprint, secrets = await asyncio.to_thread(self._prepare, record)
        return await self._submit(record, blueprint, secrets)

    async def _fire_due(self, record: ScheduleRecord, now: datetime) -> None:
        """Advance one due schedule: resolve misfires, stamp the next slot, submit the fires."""
        try:
            trigger = parse_trigger(record.trigger)
            policy = misfire_policy(record.trigger)
        except AetheriusError:
            # Only hand-edited store rows can get here (CLI and API validate on write). Disable
            # instead of retrying a permanently broken row every tick; it stays visible in list.
            _log.exception("Schedule %s has an invalid trigger; disabling it.", record.id)
            disabled = record.model_copy(update={"enabled": False})
            await asyncio.to_thread(self._store.schedules.update, disabled)
            return

        due_at = record.next_run_at
        assert due_at is not None  # due() filters on next_run_at
        if now - due_at <= self._grace:
            fires: list[datetime] = [due_at]
        else:
            fires = resolve_misfires(trigger, due_at, now, policy)

        # Advance the slot before submitting anything: an overlapping tick sees the schedule as no
        # longer due and cannot replay it. A skip resolution moves the slot without stamping a fire.
        upcoming = next_run_at(trigger, now)
        if fires:
            await asyncio.to_thread(self._store.schedules.mark_fired, record.id, upcoming)
        else:
            rescheduled = record.model_copy(update={"next_run_at": upcoming})
            await asyncio.to_thread(self._store.schedules.update, rescheduled)
            return

        for _ in fires:
            try:
                blueprint, secrets = await asyncio.to_thread(self._prepare, record)
                await self._submit(record, blueprint, secrets)
            except AetheriusError as exc:
                # A broken schedule (Blueprint moved, invalid file) must be observable: it lands in
                # the run history as a failed run and goes through the failure alert policy.
                await asyncio.to_thread(self._record_failure, record, str(exc))

    def _prepare(self, record: ScheduleRecord) -> tuple[Blueprint, dict[str, str]]:
        """Load the Blueprint and resolve secret values at fire time (worker thread)."""
        return load_blueprint(record.blueprint), resolve_secrets(record.secrets, None)

    async def _submit(
        self,
        record: ScheduleRecord,
        blueprint: Blueprint,
        secrets: Mapping[str, str],
    ) -> str:
        run_id = await self._manager.submit(
            blueprint, record.inputs, secrets, schedule_id=record.id
        )
        follower = asyncio.create_task(self._follow(record, run_id, secrets))
        self._followers.add(follower)
        follower.add_done_callback(self._followers.discard)
        return run_id

    async def _follow(
        self, record: ScheduleRecord, run_id: str, secrets: Mapping[str, str]
    ) -> None:
        """Wait for a submitted run to finish, then apply the schedule's alert policy."""
        job = self._manager.get(run_id)
        if job is None:
            return
        await job.finished.wait()
        status = job.result.status.value if job.result is not None else "failed"
        outputs = job.result.outputs if job.result is not None else {}
        await asyncio.to_thread(
            apply_notify_policy,
            record,
            status=status,
            error=job.error,
            outputs=outputs,
            secrets=secrets,
            store=self._store,
        )

    def _record_failure(self, record: ScheduleRecord, error: str) -> None:
        """Persist a run that failed before reaching the engine, and alert per policy."""
        now = datetime.now(timezone.utc)
        self._store.runs.record(
            RunRecord(
                run_id=uuid.uuid4().hex,
                blueprint_name=record.blueprint,
                status="failed",
                schedule_id=record.id,
                error=error,
                started_at=now,
                finished_at=now,
            )
        )
        apply_notify_policy(
            record, status="failed", error=error, outputs={}, secrets={}, store=self._store
        )
