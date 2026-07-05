"""Profile warmup: build an authentic browsing history before automation.

A persistent profile that jumps straight to a sensitive target on its very first request looks
synthetic. Warmup visits a few innocuous pages first, dwelling on each, so the profile accrues real
cookies, cache and history — the human touch a cold profile lacks. Generalizes the manual
login-setup flow of the legacy projects.

:func:`plan_warmup` is pure (the itinerary and dwell times, deterministic given an ``rng``);
:func:`warmup_profile` plays it against a page. Kept intentionally small.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from random import Random
from typing import Any

from ..humanizer.timing import Sleeper, precise_sleep

_DEFAULT_DWELL_MS = 2000.0
_DEFAULT_RNG = Random()


@dataclass(frozen=True, slots=True)
class WarmupStep:
    """One warmup visit: a URL and how long (seconds) to dwell before moving on."""

    url: str
    dwell_s: float


@dataclass(frozen=True, slots=True)
class WarmupPlan:
    """An ordered warmup itinerary."""

    steps: list[WarmupStep]


def plan_warmup(
    urls: Iterable[str], *, dwell_ms: float = _DEFAULT_DWELL_MS, rng: Random = _DEFAULT_RNG
) -> WarmupPlan:
    """Build a warmup itinerary from *urls*, each with a randomized dwell around *dwell_ms*."""
    steps = [WarmupStep(url, rng.uniform(dwell_ms * 0.6, dwell_ms * 1.4) / 1000.0) for url in urls]
    return WarmupPlan(steps)


def warmup_profile(page: Any, plan: WarmupPlan, *, sleep: Sleeper = precise_sleep) -> None:
    """Play *plan* against a page: navigate to each URL and dwell, accreting authentic history."""
    for step in plan.steps:
        page.goto(step.url)
        sleep(step.dwell_s)
