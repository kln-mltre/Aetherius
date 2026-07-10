"""Tests for stealth/humanizer/scroll.py — the eased wheel curve."""

from __future__ import annotations

from random import Random
from unittest.mock import MagicMock

import pytest

from aetherius.stealth.humanizer.scroll import ease_out_deltas, human_scroll

pytestmark = pytest.mark.unit


def test_deltas_sum_to_amount() -> None:
    deltas = ease_out_deltas(600.0, 800.0)
    assert sum(d for d, _ in deltas) == pytest.approx(600.0)


def test_ease_out_front_loads_movement() -> None:
    deltas = [d for d, _ in ease_out_deltas(600.0, 800.0)]
    # Ease-out means the first step moves further than the last.
    assert deltas[0] > deltas[-1]


def test_human_scroll_drives_wheel_for_every_step() -> None:
    page = MagicMock()
    human_scroll(page, 300.0, duration_ms=120.0, rng=Random(0), sleep=lambda _: None)
    calls = page.mouse.wheel.call_args_list
    assert len(calls) == len(ease_out_deltas(300.0, 120.0))
    total = sum(call.args[1] for call in calls)
    assert total == pytest.approx(300.0)
