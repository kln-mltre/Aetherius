"""Unit tests for recorder/gesture_recorder.py: pure segmentation and library merge (no browser)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.recorder.gesture_recorder import merge_into_library, segment_gestures
from aetherius.stealth.gestures.library import GestureLibrary

pytestmark = pytest.mark.unit


def _aimed_move(x0: float, y0: float, x1: float, y1: float, t0: float, steps: int = 30) -> list:
    """A dense straight move sampled as absolute [x, y, t] points."""
    return [
        (
            x0 + (x1 - x0) * i / steps,
            y0 + (y1 - y0) * i / steps,
            round(t0 + i * 0.01, 4),
        )
        for i in range(steps + 1)
    ]


def test_segments_split_on_clicks_and_rebase_to_offsets() -> None:
    move_a = _aimed_move(200, 200, 300, 200, 0.0)
    move_b = _aimed_move(300, 200, 300, 320, 1.0)
    clicks = [move_a[-1][2] + 1e-3, move_b[-1][2] + 1e-3]

    gestures = segment_gestures(move_a + move_b, clicks)

    assert len(gestures) == 2
    # Rebased: every gesture starts at the origin.
    assert gestures[0][0] == (0.0, 0.0, 0.0)
    assert gestures[1][0] == (0.0, 0.0, 0.0)
    # And ends at the total displacement of its move.
    assert gestures[0][-1][0] == pytest.approx(100.0, abs=1.0)
    assert gestures[1][-1][1] == pytest.approx(120.0, abs=1.0)


def test_degenerate_moves_are_dropped() -> None:
    tiny = [(10.0, 10.0, 0.0), (11.0, 10.0, 0.01)]  # 2 points, ~1px: below both thresholds
    assert segment_gestures(tiny, clicks=[0.02]) == []


def test_a_long_pause_starts_a_new_gesture() -> None:
    first = _aimed_move(0, 0, 120, 0, 0.0)
    # Same continuous stream but with a 1s gap before the second move and no clicks at all.
    second = _aimed_move(120, 0, 120, 140, first[-1][2] + 1.0)
    gestures = segment_gestures(first + second, clicks=[])
    assert len(gestures) == 2


def test_merge_is_non_destructive_and_marks_recorded_provenance(tmp_path: Path) -> None:
    path = tmp_path / "human_library.json"
    g1 = segment_gestures(_aimed_move(0, 0, 150, 0, 0.0), clicks=[0.31])
    added_first = merge_into_library(path, g1)
    assert added_first == 1

    g2 = segment_gestures(_aimed_move(0, 0, 0, 180, 0.0), clicks=[0.31])
    added_second = merge_into_library(path, g2)
    assert added_second == 1

    data = json.loads(path.read_text())
    assert data["meta"]["source"] == "recorded-human"
    assert len(data["gestures"]) == 2  # first batch preserved, second appended

    # The written file is a valid, matchable library for the stealth humanizer.
    library = GestureLibrary.from_data(data)
    assert len(library) == 2
