"""In-daemon scheduler (Phase 1.5, Jalon D).

Re-runs Blueprints on a cron or interval trigger. It lives under ``server/`` so it is only imported
when the daemon runs (``aetherius serve``); ``import aetherius`` stays light. The service polls the
durable store (``aetherius.store``) each tick, submits due schedules through the daemon's
``RunManager``, records outcomes back to the store, and applies the per-schedule alert policy via
``aetherius.notify``. Cron math is delegated to ``croniter`` (pure-python, light).

Status: jalon en attente. Public shape fixed here; implementation lands with Jalon D.
See docs/phase-1.5/d-scheduler.md.
"""

from __future__ import annotations

from .service import SchedulerService
from .triggers import Trigger, next_run_at

__all__ = ["SchedulerService", "Trigger", "next_run_at"]
