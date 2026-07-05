"""Tests for stealth/humanizer/input.py — the HumanInput facade and its per-feature degradation."""

from __future__ import annotations

from random import Random
from unittest.mock import MagicMock

import pytest

from aetherius.stealth.gestures.library import GestureLibrary
from aetherius.stealth.humanizer.input import HumanInput
from aetherius.stealth.policy import StealthPolicy

pytestmark = pytest.mark.unit


def _library() -> GestureLibrary:
    return GestureLibrary.from_data({"gestures": [[(0.0, 0.0, 0.0), (100.0, 0.0, 0.1)]]})


def _locator() -> MagicMock:
    locator = MagicMock()
    locator.bounding_box.return_value = {"x": 10.0, "y": 20.0, "width": 100.0, "height": 40.0}
    return locator


def _human(policy: StealthPolicy) -> tuple[HumanInput, MagicMock]:
    page = MagicMock()
    human = HumanInput(page, policy, rng=Random(0), sleep=lambda _: None, library=_library())
    return human, page


def test_click_uses_gesture_mouse_when_enabled() -> None:
    human, page = _human(StealthPolicy(mouse="gestures"))
    human.click(_locator())
    page.mouse.down.assert_called_once()  # went through the humanized mouse


def test_click_falls_back_to_plain_locator_when_mouse_off() -> None:
    human, page = _human(StealthPolicy(keyboard="human"))
    locator = _locator()
    human.click(locator)
    locator.click.assert_called_once()
    page.mouse.down.assert_not_called()


def test_fill_clears_then_types_humanly() -> None:
    human, page = _human(StealthPolicy(mouse="gestures", keyboard="human"))
    human.fill(_locator(), "abc")
    presses = [c.args[0] for c in page.keyboard.press.call_args_list]
    assert "Control+a" in presses and "Delete" in presses
    typed = [c.args[0] for c in page.keyboard.type.call_args_list]
    assert typed == ["a", "b", "c"]  # keyboard humanizer types char by char


def test_type_without_keyboard_feature_uses_plain_type() -> None:
    human, page = _human(StealthPolicy(mouse="gestures"))  # keyboard off
    human.type(_locator(), "hi")
    page.keyboard.type.assert_called_once_with("hi")


def test_scroll_by_drives_the_wheel() -> None:
    human, page = _human(StealthPolicy(scroll="eased"))
    human.scroll_by(250.0)
    assert page.mouse.wheel.called
