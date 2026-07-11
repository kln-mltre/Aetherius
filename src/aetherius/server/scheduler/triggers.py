"""Trigger types and next-fire computation.

A schedule stores its firing rule as an opaque dict (``ScheduleRecord.trigger``); the scheduler
parses it into a :class:`Trigger` and asks :func:`next_run_at` when the rule next fires. Cron
expressions are evaluated with ``croniter`` (added to the base dependencies for Jalon D).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TriggerKind = Literal["cron", "interval", "at"]

_PENDING = "Jalon 1.5-D (scheduler): trigger math not implemented yet."


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


def next_run_at(trigger: Trigger, after: datetime) -> datetime | None:
    """Return the next fire time strictly after *after*, or None if the trigger is exhausted."""
    raise NotImplementedError(_PENDING)
