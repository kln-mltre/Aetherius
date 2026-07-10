"""Human scrolling: a cubic ease-out wheel curve instead of one instantaneous jump.

Real wheel scrolling decelerates — fast at first, easing to a stop — so a single large
``mouse.wheel`` delta reads as automation. :func:`ease_out_deltas` turns a target distance into a
sequence of per-frame ``(delta, dt)`` steps following a cubic ease-out; it is pure, so the curve is
unit-tested without a browser. :func:`human_scroll` simply plays those steps against a page.
"""

from __future__ import annotations

from random import Random
from typing import Any, Callable

from .timing import Sleeper, precise_sleep

# ~12 ms per step tracks a 60 fps frame budget, giving visually smooth motion without flooding the
# input queue with wheel events.
_STEP_MS = 12.0
_DEFAULT_RNG = Random()


def ease_out_deltas(
    amount: float, duration_ms: float, step_ms: float = _STEP_MS
) -> list[tuple[float, float]]:
    """Break a scroll of *amount* px over *duration_ms* into ``(delta_px, dt_s)`` ease-out steps.

    Cubic ease-out (``1 - (1 - t)^3``) front-loads the movement and settles softly. Per-step deltas
    are differences of the eased cumulative offset, so they sum exactly to *amount*.
    """
    steps = max(1, int(duration_ms / step_ms))
    dt = step_ms / 1000.0
    deltas: list[tuple[float, float]] = []
    last = 0.0
    for i in range(1, steps + 1):
        t = i / steps
        eased = amount * (1.0 - (1.0 - t) ** 3)
        deltas.append((eased - last, dt))
        last = eased
    return deltas


def human_scroll(
    page: Any,
    amount: float,
    *,
    duration_ms: float | None = None,
    rng: Random = _DEFAULT_RNG,
    sleep: Sleeper = precise_sleep,
) -> None:
    """Scroll the page vertically by *amount* px with an eased, stepped wheel motion."""
    total_ms = duration_ms if duration_ms is not None else rng.uniform(600.0, 1000.0)
    wheel: Callable[[float, float], None] = page.mouse.wheel
    for delta, dt in ease_out_deltas(amount, total_ms):
        wheel(0.0, delta)
        sleep(dt)
