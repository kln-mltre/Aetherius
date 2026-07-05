"""Deterministic generator for the bundled synthetic gesture seed.

The mouse humanizer replays gestures from a library, but the recorder that captures *real* human
traces is a later milestone. So the package ships a small seed of algorithmically generated traces
so ``mouse: gestures`` works — and can be tested against a real browser — from day one. Each trace
follows a minimum-jerk velocity profile (the textbook model of aimed human reaching), with a slight
terminal overshoot and perpendicular tremor for realism. Because it is seeded, the output is
reproducible; because :mod:`.library` is source-agnostic, real recorded or model-generated traces
drop into the exact same format later (``meta.source`` marks the origin).

Regenerate with ``python -m aetherius.stealth.gestures.seed``. Pure stdlib: no numpy.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from random import Random

from .library import Point

# Distance/direction grid the seed covers, so best_match always finds a close shape for any move.
_DISTANCES = (60.0, 120.0, 200.0, 300.0, 450.0, 620.0)
_DIRECTIONS = 8  # cardinal + diagonal


def _min_jerk(tau: float) -> float:
    """Minimum-jerk position profile in [0, 1]: smooth ease-in then ease-out over normalized time."""
    return tau**3 * (10.0 - 15.0 * tau + 6.0 * tau**2)


def generate_gesture(dx: float, dy: float, *, rng: Random) -> list[Point]:
    """Generate one trace from the origin to ``(dx, dy)`` as ``[x, y, t]`` offset points.

    Sample count scales with distance (more points for longer moves), duration follows a loose
    speed–distance law, tremor and a small overshoot are largest mid-flight and vanish at the ends
    so the trace starts at the origin and lands exactly on the target.
    """
    distance = math.hypot(dx, dy)
    ux, uy = (dx / distance, dy / distance) if distance else (0.0, 0.0)
    perp_x, perp_y = -uy, ux  # unit vector perpendicular to the direction of travel

    samples = max(12, min(40, int(distance / 8)))
    duration = 0.18 + distance / 1400.0 + rng.uniform(-0.03, 0.05)
    tremor = rng.uniform(0.6, 1.8)
    overshoot = rng.uniform(0.01, 0.035) * distance

    points: list[Point] = []
    for i in range(samples + 1):
        tau = i / samples
        bell = math.sin(math.pi * tau)  # 0 at both ends, 1 at mid-flight
        progress = _min_jerk(tau)
        along = progress * distance + (overshoot * bell if tau > 0.6 else 0.0)
        wobble = tremor * bell * rng.uniform(-1.0, 1.0)
        x = ux * along + perp_x * wobble
        y = uy * along + perp_y * wobble
        t = tau * duration
        points.append((round(x, 2), round(y, 2), round(t, 4)))

    points[0] = (0.0, 0.0, 0.0)
    points[-1] = (round(dx, 2), round(dy, 2), points[-1][2])
    return points


def generate_library(*, seed: int = 20240705) -> dict[str, object]:
    """Build the full seed library dict (``meta`` + ``gestures``), deterministic given *seed*."""
    rng = Random(seed)
    gestures: list[list[Point]] = []
    for distance in _DISTANCES:
        for k in range(_DIRECTIONS):
            angle = (2 * math.pi * k / _DIRECTIONS) + rng.uniform(-0.12, 0.12)
            gestures.append(
                generate_gesture(distance * math.cos(angle), distance * math.sin(angle), rng=rng)
            )
    return {
        "meta": {
            "source": "synthetic-seed",
            "model": "min-jerk+overshoot+tremor",
            "generator": "aetherius.stealth.gestures.seed",
            "seed": seed,
            "note": "Bootstrap seed; the gesture recorder adds real human traces via the same format.",
        },
        "gestures": gestures,
    }


def write_seed(path: Path | None = None) -> Path:
    """Write the seed library to disk (defaults to the packaged data file) and return its path."""
    target = path or (Path(__file__).resolve().parent / "data" / "human_library.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(generate_library(), indent=1), encoding="utf-8")
    return target


if __name__ == "__main__":  # pragma: no cover - manual regeneration entry point
    print(f"Wrote gesture seed to {write_seed()}")
