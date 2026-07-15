"""Schedules section of the Console: list, detail (history + manual fire) and guided form.

The Console counterpart of ``aetherius schedule …`` and ``/v1/schedules`` — same store, same
validation helpers (``server/scheduler``), zero JSON by hand. Split like ``screens/builder/``:
one module per screen, plus shared formatting helpers in ``_common.py``.
"""

from __future__ import annotations

from .screen import SchedulesScreen

__all__ = ["SchedulesScreen"]
