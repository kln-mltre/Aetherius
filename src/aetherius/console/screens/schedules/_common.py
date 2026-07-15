"""Helpers shared by the Schedules screens: store access, formatting, enabled toggling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ....server.scheduler import next_run_at, parse_trigger
from ....store import ScheduleRecord, Store


def get_default_store() -> Store:
    """The process-wide store; isolated stores are injected by tests and screenshots."""
    from ....store import get_store

    return get_store()


def format_local(value: datetime | None) -> str:
    """Local wall-clock rendering for the tables, '-' when unset (same idiom as the CLI)."""
    return value.astimezone().strftime("%Y-%m-%d %H:%M") if value is not None else "-"


def notify_summary(policy: Mapping[str, Any]) -> str:
    """One-liner for a schedule's notify policy ('ntfy · on change', '-' when alerting is off)."""
    channel = policy.get("channel")
    if not channel:
        return "-"
    return f"{channel} · on {policy.get('on', 'failure')}"


def toggle_enabled(store: Store, record: ScheduleRecord) -> ScheduleRecord:
    """Pause or resume *record* and persist it; returns the updated record.

    Resuming restarts the cadence from now (same rule as the API PATCH and ``schedule resume``):
    the paused window must never be caught up as a misfire.
    """
    if record.enabled:
        updated = record.model_copy(update={"enabled": False})
    else:
        upcoming = next_run_at(parse_trigger(record.trigger), datetime.now(timezone.utc))
        updated = record.model_copy(update={"enabled": True, "next_run_at": upcoming})
    store.schedules.update(updated)
    return updated
