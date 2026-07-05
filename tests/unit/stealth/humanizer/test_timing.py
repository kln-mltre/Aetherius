"""Tests for stealth/humanizer/timing.py — precise sleep and distracted pauses."""

from __future__ import annotations

from random import Random

import pytest

from aetherius.stealth.humanizer.timing import human_pause, precise_sleep

pytestmark = pytest.mark.unit


def test_precise_sleep_non_positive_is_noop() -> None:
    precise_sleep(0)
    precise_sleep(-1)  # must not raise or hang


def test_human_pause_within_range_without_distraction() -> None:
    slept: list[float] = []
    duration = human_pause(0.1, 0.2, 0.0, rng=Random(0), sleep=slept.append)
    assert 0.1 <= duration <= 0.2
    assert slept == [duration]


def test_human_pause_distraction_extends_duration() -> None:
    # distraction=1.0 always fires; the extra 1.5-4.0s pushes well past the base window.
    duration = human_pause(0.1, 0.2, 1.0, rng=Random(0), sleep=lambda _: None)
    assert duration > 0.2 + 1.0
