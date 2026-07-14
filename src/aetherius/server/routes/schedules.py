"""Schedule endpoints: durable CRUD plus an immediate manual fire.

The store is the single source of truth shared with the CLI (which writes to it directly, daemon
up or not); these routes serve the programmatic/SDK surface. Store access runs on worker threads
(``asyncio.to_thread``) so a contended SQLite write can never stall the event loop.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.errors import AetheriusError, ScheduleError
from ...store import ScheduleRecord, Store
from ..deps import get_scheduler, get_store, require_auth
from ..scheduler import (
    SchedulerService,
    misfire_policy,
    next_run_at,
    parse_trigger,
    validate_notify_policy,
)
from ..schemas import RunHandle, ScheduleCreate, ScheduleUpdate

router = APIRouter(prefix="/v1", tags=["schedules"], dependencies=[Depends(require_auth)])


def _validated_next_run(trigger: Mapping[str, Any], now: datetime) -> datetime | None:
    """Validate a trigger dict (rule + misfire policy) and compute its first fire after *now*.

    Semantic problems answer 422, mirroring how a structurally broken Blueprint fails fast.
    """
    try:
        parsed = parse_trigger(trigger)
        misfire_policy(trigger)
    except ScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return next_run_at(parsed, now)


def _validated_notify(notify: Mapping[str, Any]) -> None:
    try:
        validate_notify_policy(notify)
    except ScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


async def _get_or_404(store: Store, schedule_id: str) -> ScheduleRecord:
    record = await asyncio.to_thread(store.schedules.get, schedule_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown schedule {schedule_id!r}."
        )
    return record


@router.post("/schedules", status_code=status.HTTP_201_CREATED, response_model=ScheduleRecord)
async def create_schedule(
    body: ScheduleCreate, store: Store = Depends(get_store)
) -> ScheduleRecord:
    now = datetime.now(timezone.utc)
    _validated_notify(body.notify)
    record = ScheduleRecord(
        id=uuid.uuid4().hex,
        name=body.name,
        blueprint=body.blueprint,
        inputs=body.inputs,
        secrets=body.secrets,
        trigger=body.trigger,
        notify=body.notify,
        enabled=body.enabled,
        created_at=now,
        next_run_at=_validated_next_run(body.trigger, now),
    )
    await asyncio.to_thread(store.schedules.create, record)
    return record


@router.get("/schedules", response_model=list[ScheduleRecord])
async def list_schedules(store: Store = Depends(get_store)) -> list[ScheduleRecord]:
    return await asyncio.to_thread(store.schedules.all)


@router.get("/schedules/{schedule_id}", response_model=ScheduleRecord)
async def get_schedule(schedule_id: str, store: Store = Depends(get_store)) -> ScheduleRecord:
    return await _get_or_404(store, schedule_id)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleRecord)
async def update_schedule(
    schedule_id: str, body: ScheduleUpdate, store: Store = Depends(get_store)
) -> ScheduleRecord:
    record = await _get_or_404(store, schedule_id)
    changes = body.model_dump(exclude_unset=True)
    if "notify" in changes:
        _validated_notify(changes["notify"])

    # A changed rule or a resume restarts the cadence from now: the paused (or stale) window is
    # deliberately not treated as a misfire to catch up on.
    resumed = changes.get("enabled") is True and not record.enabled
    if "trigger" in changes or resumed:
        trigger = changes.get("trigger", record.trigger)
        changes["next_run_at"] = _validated_next_run(trigger, datetime.now(timezone.utc))

    updated = record.model_copy(update=changes)
    await asyncio.to_thread(store.schedules.update, updated)
    return updated


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: str, store: Store = Depends(get_store)) -> None:
    await _get_or_404(store, schedule_id)
    await asyncio.to_thread(store.schedules.delete, schedule_id)


@router.post(
    "/schedules/{schedule_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunHandle,
)
async def run_schedule(
    schedule_id: str,
    store: Store = Depends(get_store),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> RunHandle:
    """Fire the schedule immediately, without touching its cadence (``next_run_at`` stays put)."""
    record = await _get_or_404(store, schedule_id)
    try:
        run_id = await scheduler.fire_now(record)
    except AetheriusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return RunHandle(run_id=run_id)
