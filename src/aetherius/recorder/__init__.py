"""Recorders that generate artifacts: Blueprints from a live session, and mouse gestures for the stealth library.

Public entry points are re-exported here. None of the imports pull Playwright at module load: the
browser is imported lazily inside the recording functions, so ``import aetherius`` stays light.
"""

from __future__ import annotations

from .blueprint_recorder import describe_event, record_blueprint
from .gesture_recorder import record_gestures

__all__ = ["record_blueprint", "record_gestures", "describe_event"]
