"""Trigger types and next-fire computation.

A schedule stores its firing rule as an opaque dict (``ScheduleRecord.trigger``); the scheduler
parses it into a :class:`Trigger` and asks :func:`next_run_at` when the rule next fires. Cron
expressions are evaluated with ``croniter`` in the host's **local timezone** (a user writing
``0 0,3 * * *`` means local midnight and 3am; croniter absorbs DST shifts), but every datetime
returned or accepted here is **UTC-aware**: the store orders ``next_run_at`` as ISO-8601 text, which
is only correct under a single timezone convention (see docs/store.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping

from croniter import croniter
from tzlocal import get_localzone

from ...core.errors import ScheduleError

TriggerKind = Literal["cron", "interval", "at"]


@dataclass(frozen=True)
class Trigger:
    """A schedule's firing rule.

    - ``cron``: ``expr`` is a 5-field cron string (e.g. ``"0 0,3 * * *"`` for midnight and 3am).
    - ``interval``: ``seconds`` between fires.
    - ``at``: a single ``when`` datetime (one-shot).
    """

    kind: TriggerKind
    expr: str | None = None
    seconds: int | None = None
    when: datetime | None = None


def parse_trigger(data: Mapping[str, Any]) -> Trigger:
    """Validate an opaque trigger dict from the store or the API into a :class:`Trigger`.

    Raises:
        ScheduleError: unknown kind, missing or malformed field for the kind.
    """
    kind = data.get("kind")
    if kind == "cron":
        expr = data.get("expr")
        if not isinstance(expr, str) or not croniter.is_valid(expr):
            raise ScheduleError(f"Invalid cron expression {expr!r} (expected 5 fields).")
        return Trigger(kind="cron", expr=expr)
    if kind == "interval":
        seconds = data.get("seconds")
        if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
            raise ScheduleError(f"Invalid interval {seconds!r}: 'seconds' must be a positive int.")
        return Trigger(kind="interval", seconds=seconds)
    if kind == "at":
        raw = data.get("when")
        when: datetime | None = raw if isinstance(raw, datetime) else None
        if isinstance(raw, str):
            try:
                when = datetime.fromisoformat(raw)
            except ValueError:
                when = None
        if when is None:
            raise ScheduleError(
                f"Invalid 'at' trigger: 'when' must be an ISO datetime, got {raw!r}."
            )
        return Trigger(kind="at", when=_as_utc(when))
    raise ScheduleError(f"Unknown trigger kind {kind!r}; expected 'cron', 'interval' or 'at'.")


def next_run_at(trigger: Trigger, after: datetime) -> datetime | None:
    """Return the next fire time strictly after *after*, or None if the trigger is exhausted."""
    after = _as_utc(after)
    if trigger.kind == "cron":
        assert trigger.expr is not None
        # Evaluate in local time so the expression means what a crontab means on this host, then
        # normalize back to UTC for storage and comparison. The IANA zone (tzlocal), not a fixed
        # offset from astimezone(): croniter needs the real DST rules for wall-clock math.
        local_next: datetime = croniter(trigger.expr, after.astimezone(get_localzone())).get_next(
            datetime
        )
        return local_next.astimezone(timezone.utc)
    if trigger.kind == "interval":
        assert trigger.seconds is not None
        return after + timedelta(seconds=trigger.seconds)
    assert trigger.when is not None
    return trigger.when if trigger.when > after else None


def _as_utc(value: datetime) -> datetime:
    """Normalize to UTC; a naive datetime is interpreted as local time (CLI convenience)."""
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc)
