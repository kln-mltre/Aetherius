"""Tests for stealth/humanizer/mouse.py — geometric gesture replay and clicking."""

from __future__ import annotations

import math
from random import Random
from unittest.mock import MagicMock

import pytest

from aetherius.stealth.gestures.library import GestureLibrary
from aetherius.stealth.humanizer.mouse import HumanMouse, _rotate, plan_replay

pytestmark = pytest.mark.unit


def _library() -> GestureLibrary:
    # A couple of simple, clean traces are enough to exercise matching + transform.
    return GestureLibrary.from_data(
        {
            "gestures": [
                [(0.0, 0.0, 0.0), (50.0, 0.0, 0.05), (100.0, 0.0, 0.1)],
                [(0.0, 0.0, 0.0), (0.0, 50.0, 0.05), (0.0, 100.0, 0.1)],
            ]
        }
    )


def test_rotate_quarter_turn() -> None:
    x, y = _rotate(1.0, 0.0, math.pi / 2)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0)


def test_plan_replay_lands_exactly_on_target() -> None:
    gesture = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.1)]
    points = plan_replay(gesture, (500.0, 300.0), (700.0, 360.0))
    assert points[-1][:2] == (700.0, 360.0)


def test_plan_replay_skips_trivial_moves() -> None:
    assert plan_replay([(0.0, 0.0, 0.0), (1.0, 0.0, 0.1)], (10.0, 10.0), (10.2, 10.0)) == []


def test_move_to_updates_virtual_cursor_and_drives_mouse() -> None:
    page = MagicMock()
    mouse = HumanMouse(page, _library(), rng=Random(0), sleep=lambda _: None)
    mouse.move_to(650.0, 300.0)
    assert (mouse.x, mouse.y) == (650.0, 300.0)
    assert page.mouse.move.call_args_list[-1].args == (650.0, 300.0)


def test_click_presses_and_releases_once() -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.bounding_box.return_value = {"x": 10.0, "y": 20.0, "width": 100.0, "height": 40.0}
    mouse = HumanMouse(page, _library(), rng=Random(0), sleep=lambda _: None)
    mouse.click(locator)
    page.mouse.down.assert_called_once()
    page.mouse.up.assert_called_once()


def test_move_to_locator_without_box_is_noop() -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.bounding_box.return_value = None
    mouse = HumanMouse(page, _library(), rng=Random(0), sleep=lambda _: None)
    mouse.move_to_locator(locator)
    page.mouse.move.assert_not_called()


def test_move_to_locator_scrolls_target_into_view_first() -> None:
    # An off-screen target must be scrolled in before its box coordinates are read, or the click
    # would land on nothing.
    page = MagicMock()
    locator = MagicMock()
    locator.bounding_box.return_value = {"x": 10.0, "y": 20.0, "width": 100.0, "height": 40.0}
    mouse = HumanMouse(page, _library(), rng=Random(0), sleep=lambda _: None)
    mouse.move_to_locator(locator)
    locator.scroll_into_view_if_needed.assert_called_once_with()


def test_park_drifts_cursor_toward_the_bottom() -> None:
    page = MagicMock()
    page.evaluate.return_value = {"width": 1200, "height": 800}
    mouse = HumanMouse(page, _library(), rng=Random(0), sleep=lambda _: None)
    mouse.park()
    x, y = page.mouse.move.call_args_list[-1].args
    assert 50.0 <= x <= 1150.0
    assert 750.0 <= y <= 780.0  # height minus a small margin
