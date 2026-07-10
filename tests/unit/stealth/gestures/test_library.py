"""Tests for stealth/gestures/library.py — downsampling, analysis and matching."""

from __future__ import annotations

import math
from random import Random

import pytest

from aetherius.stealth.gestures.library import GestureLibrary, _downsample, default_library

pytestmark = pytest.mark.unit


def test_downsample_keeps_endpoints_and_thins_middle() -> None:
    points = [(0.0, 0.0, 0.0), (0.5, 0.0, 0.01), (1.0, 0.0, 0.02), (100.0, 0.0, 0.2)]
    kept = _downsample(points, min_dist=3.0)
    assert kept[0] == points[0]
    assert kept[-1] == points[-1]
    # The near-duplicate second point is dropped; endpoints and the far point remain.
    assert len(kept) < len(points)


def test_from_data_ignores_degenerate_gestures() -> None:
    data = {"gestures": [[(0.0, 0.0, 0.0)], [(0.0, 0.0, 0.0), (100.0, 0.0, 0.1)]]}
    lib = GestureLibrary.from_data(data)
    assert len(lib) == 1  # the single-point gesture is dropped


def test_best_match_prefers_matching_direction() -> None:
    right = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.1)]
    up = [(0.0, 0.0, 0.0), (0.0, 100.0, 0.1)]
    lib = GestureLibrary.from_data({"gestures": [right, up]})
    match = lib.best_match(100.0, 0.0, rng=Random(0))  # angle 0 == pointing right
    assert match is not None
    end_x, end_y, _ = match[-1]
    assert end_x > 0 and abs(end_y) < 1e-6


def test_best_match_empty_library_returns_none() -> None:
    assert GestureLibrary([]).best_match(10.0, 0.0, rng=Random(0)) is None
    assert GestureLibrary([]).is_empty is True


def test_bundled_seed_loads_and_matches() -> None:
    lib = default_library()
    assert len(lib) > 0
    assert lib.meta.get("source") == "synthetic-seed"
    match = lib.best_match(300.0, math.pi / 2, rng=Random(1))
    assert match is not None
    assert match[0] == (0.0, 0.0, 0.0)  # traces start at their own origin
