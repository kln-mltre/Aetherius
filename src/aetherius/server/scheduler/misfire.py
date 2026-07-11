"""Misfire handling: what to do with fire times missed while the daemon was down.

A local daemon is not always up (laptop asleep, host rebooting). When it starts back up, some
schedules may have a ``next_run_at`` in the past. The policy decides whether to skip those, run a
single catch-up, or replay each missed fire.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from .triggers import Trigger

_PENDING = "Jalon 1.5-D (scheduler): misfire resolution not implemented yet."


class MisfirePolicy(str, Enum):
    SKIP = "skip"  # ignore missed fires, wait for the next scheduled time
    RUN_ONCE = "run_once"  # coalesce all missed fires into one catch-up run (default)
    RUN_ALL = "run_all"  # replay every missed fire (rarely wanted)


def resolve_misfires(
    trigger: Trigger,
    last_fired: datetime | None,
    now: datetime,
    policy: MisfirePolicy,
) -> list[datetime]:
    """Return the fire times to execute now given a *policy* and the gap since *last_fired*."""
    raise NotImplementedError(_PENDING)
