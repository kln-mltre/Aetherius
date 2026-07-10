"""Gesture library: load, downsample, analyze and match mouse traces by distance and angle.

Source-agnostic on purpose. A *gesture* is a list of ``[dx, dy, t]`` points — offsets from the
gesture's start (so the last point is its total displacement) and ``t`` the elapsed seconds. Where
those traces come from is irrelevant here: the bundled seed is synthetic (``meta.source``), the
gesture recorder will add real human traces, and a future model could generate them — all behind
this one interface. Matching finds the recorded trace whose shape (distance + direction) is closest
to a requested move, which the mouse humanizer then transforms geometrically onto the real target.

Generalized from the BioMouse system (see legacy_examples/). Pure stdlib ``math``: no numpy, so the
whole thing runs in the base test suite.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any

# A single sampled point: horizontal offset, vertical offset, elapsed seconds since the start.
Point = tuple[float, float, float]

_DATA_FILE = Path(__file__).resolve().parent / "data" / "human_library.json"
# Direction error is far more visible than distance error, so weight the angle term heavily.
_ANGLE_WEIGHT = 100.0
# Bound the linear scan so matching stays O(1) per mouse move regardless of library size.
_DEFAULT_SAMPLE = 50


@dataclass(frozen=True, slots=True)
class Gesture:
    """One analyzed trace: its downsampled points plus its overall distance and direction."""

    points: list[Point]
    distance: float
    angle: float


def _downsample(points: list[Point], min_dist: float = 3.0) -> list[Point]:
    """Drop points closer than *min_dist* px to the last kept one, preserving the endpoints.

    Thinning near-duplicate samples cuts the number of ``mouse.move`` calls at replay time without
    changing the perceived trajectory.
    """
    if len(points) < 3:
        return list(points)
    kept = [points[0]]
    last_x, last_y = points[0][0], points[0][1]
    for point in points[1:-1]:
        if math.hypot(point[0] - last_x, point[1] - last_y) >= min_dist:
            kept.append(point)
            last_x, last_y = point[0], point[1]
    kept.append(points[-1])
    return kept


def _analyze(points: list[Point]) -> Gesture | None:
    """Downsample a raw trace and compute its displacement vector, or ``None`` if degenerate."""
    clean = _downsample([(float(x), float(y), float(t)) for x, y, t in points])
    if len(clean) < 2:
        return None
    end_x, end_y, _ = clean[-1]
    return Gesture(points=clean, distance=math.hypot(end_x, end_y), angle=math.atan2(end_y, end_x))


class GestureLibrary:
    """An analyzed, matchable collection of gestures, independent of where they were recorded."""

    def __init__(self, gestures: list[Gesture], meta: dict[str, Any] | None = None) -> None:
        self._gestures = gestures
        self.meta = meta or {}

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "GestureLibrary":
        """Build a library from parsed JSON (``{"meta": {...}, "gestures": [...]}``)."""
        analyzed = [g for raw in data.get("gestures", []) if (g := _analyze(raw)) is not None]
        meta = data.get("meta")
        return cls(analyzed, meta if isinstance(meta, dict) else {})

    @classmethod
    def load(cls, path: Path) -> "GestureLibrary":
        """Load from a JSON file; a missing file yields an empty library (graceful degradation)."""
        if not path.exists():
            return cls([])
        with path.open(encoding="utf-8") as handle:
            return cls.from_data(json.load(handle))

    @property
    def is_empty(self) -> bool:
        return not self._gestures

    def __len__(self) -> int:
        return len(self._gestures)

    def best_match(
        self, distance: float, angle: float, *, rng: Random, sample_size: int = _DEFAULT_SAMPLE
    ) -> list[Point] | None:
        """Return the points of the gesture closest to (*distance*, *angle*), or ``None`` if empty.

        Only a random subsample is scored, so matching cost stays flat as the library grows while
        still drawing on its full variety across calls.
        """
        if not self._gestures:
            return None
        candidates = rng.sample(self._gestures, min(len(self._gestures), sample_size))
        best: Gesture | None = None
        best_score = math.inf
        for gesture in candidates:
            angle_diff = abs(gesture.angle - angle)
            if angle_diff > math.pi:  # normalize wrap-around to the shorter arc
                angle_diff = 2 * math.pi - angle_diff
            score = abs(gesture.distance - distance) + angle_diff * _ANGLE_WEIGHT
            if score < best_score:
                best_score = score
                best = gesture
        return best.points if best is not None else None


@lru_cache(maxsize=1)
def default_library() -> GestureLibrary:
    """The bundled gesture library, loaded once. Empty if the packaged data file is absent."""
    return GestureLibrary.load(_DATA_FILE)
