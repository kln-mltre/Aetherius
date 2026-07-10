"""Human timing primitives: precise sleep and random, occasionally distracted pauses.

``time.sleep`` has coarse OS granularity (~10-15 ms), too blunt for the sub-millisecond intervals a
replayed gesture needs, so :func:`precise_sleep` sleeps the bulk of the delay (yielding the CPU) and
busy-waits only the last ~1.5 ms where ``time.sleep`` is too coarse. :func:`human_pause` is the
"think time" between actions: a random dwell
that, now and then, stretches into a longer distraction — the kind of irregular rhythm a real user
produces and a fixed delay never does.

``rng`` and ``sleep`` are injectable so tests stay deterministic and instant.
"""

from __future__ import annotations

import time
from random import Random
from typing import Callable

# Busy-wait only this final tail, where OS sleep granularity is too coarse to hit the deadline; the
# bulk is a real ``time.sleep`` so a core is never pinned. Keeps the daemon responsive under multi-run.
_SPIN_TAIL_S = 0.0015

Sleeper = Callable[[float], None]
_DEFAULT_RNG = Random()


def precise_sleep(duration: float) -> None:
    """Sleep *duration* seconds accurately: coarse ``time.sleep`` for the bulk, then spin the tail.

    A pure busy-wait would pin a CPU core for the whole delay — untenable when the daemon replays
    several sessions at once and every gesture point calls this. So we yield the CPU for all but the
    last ``_SPIN_TAIL_S`` and only spin that short remainder, where sleep's granularity is too coarse.
    """
    if duration <= 0:
        return
    end = time.perf_counter() + duration
    coarse = duration - _SPIN_TAIL_S
    if coarse > 0:
        time.sleep(coarse)
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
