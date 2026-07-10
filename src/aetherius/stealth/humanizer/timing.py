"""Human timing primitives: precise sleep and random, occasionally distracted pauses.

``time.sleep`` has coarse OS granularity (~10-15 ms), too blunt for the sub-millisecond intervals a
replayed gesture needs, so :func:`precise_sleep` busy-waits below a 20 ms threshold and defers to
``time.sleep`` above it. :func:`human_pause` is the "think time" between actions: a random dwell
that, now and then, stretches into a longer distraction — the kind of irregular rhythm a real user
produces and a fixed delay never does.

``rng`` and ``sleep`` are injectable so tests stay deterministic and instant.
"""

from __future__ import annotations

import time
from random import Random
from typing import Callable

# Below this, OS sleep granularity dominates, so busy-wait for accuracy; above it, yield the CPU.
_BUSY_WAIT_THRESHOLD_S = 0.02

Sleeper = Callable[[float], None]
_DEFAULT_RNG = Random()


def precise_sleep(duration: float) -> None:
    """Sleep *duration* seconds accurately, busy-waiting under 20 ms where ``time.sleep`` is too coarse."""
    if duration <= 0:
        return
    if duration > _BUSY_WAIT_THRESHOLD_S:
        time.sleep(duration)
        return
    end = time.perf_counter() + duration
    while time.perf_counter() < end:
        pass


def human_pause(
    min_s: float,
    max_s: float,
    distraction: float = 0.0,
    *,
    rng: Random = _DEFAULT_RNG,
    sleep: Sleeper = precise_sleep,
) -> float:
    """Sleep a random duration in ``[min_s, max_s]``, occasionally extended by a distraction.

    With probability *distraction* an extra 1.5-4 s is added, mimicking a user glancing away. Returns
    the total slept, so callers (and tests) can observe the decision without timing the wall clock.
    """
    duration = rng.uniform(min_s, max_s)
    if distraction > 0 and rng.random() < distraction:
        duration += rng.uniform(1.5, 4.0)
    sleep(duration)
    return duration
