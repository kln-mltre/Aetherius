"""Tests for acts/continuum/human_actions.py — routing interactive steps through HumanInput.

No browser: HumanInput is a MagicMock, so these assert the *routing* (which humanized call fires and
with what target/text), not the humanizer internals (covered under tests/unit/stealth/).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts.continuum import human_actions
from aetherius.stealth.policy import StealthPolicy

pytestmark = pytest.mark.unit


def _id(value: Any) -> Any:
    return value


def _human() -> MagicMock:
    human = MagicMock()
    human.page.locator.return_value = MagicMock(name="locator")
    return human


def test_click_routes_to_human_click() -> None:
    human = _human()
    human_actions.click(human, {"selector": "#btn"}, _id)
    human.page.locator.assert_called_once_with("#btn")
    human.click.assert_called_once_with(human.page.locator.return_value)


def test_fill_passes_rendered_value() -> None:
    human = _human()
    human_actions.fill(human, {"selector": "#u", "value": "bob"}, _id)
    human.fill.assert_called_once_with(human.page.locator.return_value, "bob")


def test_type_prefers_text_over_value() -> None:
    human = _human()
    human_actions.type_text(human, {"selector": "#u", "text": "hi", "value": "x"}, _id)
    human.type.assert_called_once_with(human.page.locator.return_value, "hi")


def test_scroll_delta_uses_wheel() -> None:
    human = _human()
    human_actions.scroll(human, {"dy": 300}, _id)
    human.scroll_by.assert_called_once_with(300.0)


def test_scroll_with_selector_scrolls_into_view() -> None:
    human = _human()
    human_actions.scroll(human, {"selector": "#footer"}, _id)
    human.page.locator.return_value.scroll_into_view_if_needed.assert_called_once_with()
    human.scroll_by.assert_not_called()


def test_humanized_actions_reflect_policy_flags() -> None:
    assert human_actions.humanized_actions(StealthPolicy()) == frozenset()
    mouse_only = human_actions.humanized_actions(StealthPolicy(mouse="gestures"))
    assert mouse_only == {"click", "hover", "fill", "type"}
    kb_only = human_actions.humanized_actions(StealthPolicy(keyboard="human"))
    assert kb_only == {"fill", "type"}
    assert human_actions.humanized_actions(StealthPolicy(scroll="eased")) == {"scroll"}


def test_fingerprint_only_policy_humanizes_nothing() -> None:
    # A fingerprint-only policy is active but touches no inputs, so no action is rerouted.
    assert (
        human_actions.humanized_actions(StealthPolicy(fingerprint="chrome-desktop")) == frozenset()
    )
