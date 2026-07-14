"""In-daemon scheduler (Phase 1.5, Jalon D).

Re-runs Blueprints on a cron, interval or one-shot trigger. It lives under ``server/`` so it is
only imported when the daemon runs (``aetherius serve``); ``import aetherius`` stays light. The
service polls the durable store (``aetherius.store``) each tick, submits due schedules through the
daemon's ``RunManager``, resolves misfires per policy, and applies the per-schedule alert policy
via ``aetherius.notify``. Cron math is delegated to ``croniter`` (pure-python, light).

See docs/scheduler.md.
"""

from __future__ import annotations

from .alerts import apply_notify_policy, validate_notify_policy
from .misfire import MisfirePolicy, misfire_policy, resolve_misfires
from .service import SchedulerService
from .triggers import Trigger, next_run_at, parse_trigger

__all__ = [
    "MisfirePolicy",
    "SchedulerService",
    "Trigger",
    "apply_notify_policy",
    "misfire_policy",
    "next_run_at",
    "parse_trigger",
    "resolve_misfires",
    "validate_notify_policy",
]
