"""Tests for stealth/gestures/seed.py — the deterministic synthetic gesture generator."""

from __future__ import annotations

import math
from random import Random

import pytest

from aetherius.stealth.gestures.library import GestureLibrary
from aetherius.stealth.gestures.seed import generate_gesture, generate_library

pytestmark = pytest.mark.unit


def test_generate_gesture_starts_at_origin_and_lands_on_target() -> None:
    points = generate_gesture(200.0, -120.0, rng=Random(3))
    assert points[0] == (0.0, 0.0, 0.0)
    assert points[-1][:2] == (200.0, -120.0)
    # Time is monotonically non-decreasing along the trace.
    times = [t for _, _, t in points]
    assert times == sorted(times)


def test_generation_is_deterministic() -> None:
    assert generate_library(seed=1) == generate_library(seed=1)


def test_library_covers_many_directions() -> None:
    data = generate_library(seed=7)
    lib = GestureLibrary.from_data(data)
    assert data["meta"]["source"] == "synthetic-seed"
    # A generated seed should serve any of the four cardinal directions.
    for angle in (0.0, math.pi / 2, math.pi, -math.pi / 2):
        assert lib.best_match(250.0, angle, rng=Random(0)) is not None
