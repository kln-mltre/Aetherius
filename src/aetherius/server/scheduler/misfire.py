"""Misfire handling: what to do with fire times missed while the daemon was down.

A local daemon is not always up (laptop asleep, host rebooting). When it starts back up, some
schedules may have a ``next_run_at`` in the past. The policy decides whether to skip those, run a
single catch-up, or replay each missed fire.

The policy travels inside the schedule's opaque ``trigger`` dict (``{"misfire": "skip", ...}``) so
the store schema never changes; :func:`misfire_policy` extracts it. Resolution is a pure function
of the overdue fire time, so the tick loop applies it uniformly — a restart needs no special phase.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ...core.errors import ScheduleError
from .triggers import Trigger, next_run_at


class MisfirePolicy(str, Enum):
    SKIP = "skip"  # ignore missed fires, wait for the next scheduled time
    RUN_ONCE = "run_once"  # coalesce all missed fires into one catch-up run (default)
    RUN_ALL = "run_all"  # replay every missed fire (rarely wanted)


# Safety valve for RUN_ALL: a schedule left behind for months must not flood the daemon with an
# unbounded replay. Beyond this many missed fires, the oldest are dropped (the most recent survive).
_RUN_ALL_CAP = 100


def misfire_policy(trigger_data: Mapping[str, Any]) -> MisfirePolicy:
    """Extract the misfire policy carried by a schedule's trigger dict (default ``run_once``).

    Raises:
        ScheduleError: the value is not a known policy.
    """
    raw = trigger_data.get("misfire", MisfirePolicy.RUN_ONCE.value)
    try:
        return MisfirePolicy(raw)
    except ValueError:
        allowed = ", ".join(policy.value for policy in MisfirePolicy)
        raise ScheduleError(
            f"Unknown misfire policy {raw!r}; expected one of: {allowed}."
        ) from None


def resolve_misfires(
    trigger: Trigger,
    due_at: datetime,
    now: datetime,
    policy: MisfirePolicy,
) -> list[datetime]:
    """Return the fire times to execute now for a schedule whose *due_at* slipped past *now*.

    ``skip`` fires nothing; ``run_once`` coalesces the gap into one catch-up fire; ``run_all``
    replays every slot from *due_at* to *now* (capped, most recent kept). The caller recomputes
    ``next_run_at`` from *now* afterwards regardless of policy.
    """
    if policy is MisfirePolicy.SKIP:
        return []
    if policy is MisfirePolicy.RUN_ONCE:
        return [due_at]

    fires: list[datetime] = []
    slot: datetime | None = due_at
    while slot is not None and slot <= now:
        fires.append(slot)
        slot = next_run_at(trigger, slot)
    return fires[-_RUN_ALL_CAP:]
