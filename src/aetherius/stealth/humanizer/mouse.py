"""Human mouse motion by geometric gesture replay. Generalizes the BioMouse system.

To reach an arbitrary target, pick the library gesture whose shape (distance + direction) is closest
to the required move, then transform it — uniform scale onto the target distance, rotation onto the
target direction — and replay it point by point, preserving the recorded inter-point timing. Result:
every move traces a genuinely human path rather than a straight synthetic line, and no two moves to
the same spot are identical.

:func:`plan_replay` is the pure geometric transform (unit-tested without a browser). :class:`HumanMouse`
tracks the virtual cursor and drives a Playwright mouse; ``rng`` and ``sleep`` are injectable.
"""

from __future__ import annotations

import math
import time
from random import Random
from typing import Any

from ..gestures.library import GestureLibrary, Point, default_library
from .timing import Sleeper, precise_sleep

# Off-center click band: aiming for the exact center every time is a classic bot heuristic.
_CLICK_BAND = (0.3, 0.7)
_DEFAULT_RNG = Random()


def _rotate(x: float, y: float, angle: float) -> tuple[float, float]:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a


def plan_replay(
    gesture: list[Point], start: tuple[float, float], target: tuple[float, float]
) -> list[tuple[float, float, float]]:
    """Map *gesture* (offsets from its own origin) onto the ``start -> target`` vector.

    Returns absolute ``(x, y, t)`` points — scaled and rotated so the gesture's endpoint lands on
    *target*, with a final exact-landing correction — where ``t`` is the recorded elapsed time. An
    empty list means the move is too small to be worth animating.
    """
    (sx, sy), (tx, ty) = start, target
    target_dist = math.hypot(tx - sx, ty - sy)
    if target_dist < 1.0:
        return []
    target_angle = math.atan2(ty - sy, tx - sx)

    end_x, end_y, _ = gesture[-1]
    orig_dist = math.hypot(end_x, end_y)
    orig_angle = math.atan2(end_y, end_x)
    scale = target_dist / orig_dist if orig_dist > 0 else 1.0
    rotation = target_angle - orig_angle

    points = []
    for px, py, pt in gesture:
        rx, ry = _rotate(px * scale, py * scale, rotation)
        points.append((sx + rx, sy + ry, pt))
    points.append((tx, ty, gesture[-1][2]))  # guarantee the cursor lands exactly on target
    return points


def _eased_fallback(
    start: tuple[float, float], target: tuple[float, float], steps: int = 16
) -> list[tuple[float, float, float]]:
    """A gentle eased straight-line path, used only when no gesture library is available."""
    (sx, sy), (tx, ty) = start, target
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        eased = 1.0 - (1.0 - t) ** 3
        points.append((sx + (tx - sx) * eased, sy + (ty - sy) * eased, t * 0.4))
    return points


class HumanMouse:
    """Drives a Playwright mouse along replayed human gestures, tracking the virtual cursor."""

    def __init__(
        self,
        page: Any,
        library: GestureLibrary | None = None,
        *,
        rng: Random = _DEFAULT_RNG,
        sleep: Sleeper = precise_sleep,
    ) -> None:
        self._page = page
        self._library = library if library is not None else default_library()
        self._rng = rng
        self._sleep = sleep
        # Start at a natural-looking position rather than the (0, 0) corner a fresh page reports.
        self.x = rng.uniform(400.0, 800.0)
        self.y = rng.uniform(300.0, 600.0)

    def _plan(self, target: tuple[float, float]) -> list[tuple[float, float, float]]:
        start = (self.x, self.y)
        dist = math.hypot(target[0] - self.x, target[1] - self.y)
        angle = math.atan2(target[1] - self.y, target[0] - self.x)
        gesture = self._library.best_match(dist, angle, rng=self._rng)
        if gesture is None:
            return _eased_fallback(start, target)
        return plan_replay(gesture, start, target)

    def move_to(self, x: float, y: float) -> None:
        """Move the cursor to ``(x, y)`` along a replayed gesture, honoring its recorded timing."""
        points = self._plan((x, y))
        if not points:
            return
        anchor = time.perf_counter()
        for px, py, pt in points:
            self._page.mouse.move(px, py)
            behind = pt - (time.perf_counter() - anchor)
            if behind > 0:
                self._sleep(behind)
        self.x, self.y = x, y

    def move_to_locator(self, locator: Any) -> None:
        """Move to a random point within the center band of *locator*'s bounding box.

        The element is first brought into the viewport, so its box coordinates are actually on
        screen and the coordinate-based click lands — the same "scroll to it, then reach for it" a
        person does. Without this, a click on an off-screen target would silently miss.
        """
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if not box:
            return
        self.move_to(
            box["x"] + box["width"] * self._rng.uniform(*_CLICK_BAND),
            box["y"] + box["height"] * self._rng.uniform(*_CLICK_BAND),
        )

    def _press(self) -> None:
        """Press-and-release at the current position with randomized reaction and hold timing."""
        self._sleep(self._rng.uniform(0.05, 0.1))  # reaction time after arrival
        self._page.mouse.down()
        self._sleep(self._rng.uniform(0.05, 0.1))  # natural press-hold variance
        self._page.mouse.up()

    def click(self, locator: Any) -> None:
        """Move to *locator* and click it with randomized reaction and hold timing."""
        self.move_to_locator(locator)
        self._press()

    def click_at(self, x: float, y: float) -> None:
        """Move to ``(x, y)`` along a replayed gesture and click there.

        The coordinate-based entry point for the cognitive Acts: a grounder resolves a described
        element to a viewport point, and this clicks it with the same human motion and timing as
        a locator click. Off-center placement within the element is the caller's job — it knows
        the box, this method only knows the point.
        """
        self.move_to(x, y)
        self._press()

    def park(self) -> None:
        """Idle the cursor near the bottom of the viewport, away from interactive elements.

        A natural resting behaviour during long waits: a real user's cursor drifts off the controls
        rather than hovering them. Generalizes BioMouse.park_mouse_at_bottom.
        """
        size = self._page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )
        width, height = float(size["width"]), float(size["height"])
        self.move_to(
            self._rng.uniform(50.0, max(50.0, width - 50.0)),
            height - self._rng.uniform(20.0, 50.0),
        )
