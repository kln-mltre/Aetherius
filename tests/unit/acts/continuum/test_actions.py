"""Tests for acts/continuum/actions.py — maps each action to a Playwright page op.

Uses unittest.mock so no browser is needed: these run in the base CI (no [browser] extra).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts.continuum import actions
from aetherius.core.errors import ActionError

pytestmark = pytest.mark.unit


def _id(value: Any) -> Any:
    return value


def test_navigate_calls_goto_and_returns_status() -> None:
    page = MagicMock()
    page.url = "https://ex.com/x"
    page.goto.return_value.status = 200
    out = actions.navigate(page, {"url": "https://ex.com/x"}, _id)
    page.goto.assert_called_once_with("https://ex.com/x", wait_until="load")
    assert out == {"url": "https://ex.com/x", "status": 200}


def test_navigate_requires_url() -> None:
    with pytest.raises(ActionError):
        actions.navigate(MagicMock(), {}, _id)


def test_click_uses_css_locator_by_default() -> None:
    page = MagicMock()
    actions.click(page, {"selector": "#btn"}, _id)
    page.locator.assert_called_once_with("#btn")
    page.locator.return_value.click.assert_called_once_with()


def test_fill_sets_value() -> None:
    page = MagicMock()
    actions.fill(page, {"selector": "#u", "value": "bob"}, _id)
    page.locator.return_value.fill.assert_called_once_with("bob")


def test_type_uses_press_sequentially() -> None:
    page = MagicMock()
    actions.type_text(page, {"selector": "#u", "text": "hi"}, _id)
    page.locator.return_value.press_sequentially.assert_called_once_with("hi")


def test_xpath_selector_type() -> None:
    page = MagicMock()
    actions.click(page, {"selector": "//button", "selector_type": "xpath"}, _id)
    page.locator.assert_called_once_with("xpath=//button")


def test_text_selector_type() -> None:
    page = MagicMock()
    actions.click(page, {"selector": "Log in", "selector_type": "text"}, _id)
    page.get_by_text.assert_called_once_with("Log in")


def test_press_without_selector_uses_keyboard() -> None:
    page = MagicMock()
    actions.press(page, {"key": "Enter"}, _id)
    page.keyboard.press.assert_called_once_with("Enter")


def test_press_with_selector_targets_locator() -> None:
    page = MagicMock()
    actions.press(page, {"selector": "#u", "key": "Tab"}, _id)
    page.locator.return_value.press.assert_called_once_with("Tab")


def test_scroll_without_selector_uses_wheel() -> None:
    page = MagicMock()
    actions.scroll(page, {"dy": 300}, _id)
    page.mouse.wheel.assert_called_once_with(0.0, 300.0)


def test_scroll_with_selector_scrolls_into_view() -> None:
    page = MagicMock()
    actions.scroll(page, {"selector": "#footer"}, _id)
    page.locator.return_value.scroll_into_view_if_needed.assert_called_once_with()


def test_upload_sets_input_files() -> None:
    page = MagicMock()
    actions.upload(page, {"selector": "input[type=file]", "file": "/tmp/x.png"}, _id)
    page.locator.return_value.set_input_files.assert_called_once_with("/tmp/x.png")


def test_drag_and_drop() -> None:
    page = MagicMock()
    actions.drag(page, {"from": "#a", "to": "#b"}, _id)
    page.drag_and_drop.assert_called_once_with("#a", "#b")


def test_unknown_selector_type_raises() -> None:
    with pytest.raises(ActionError):
        actions.click(MagicMock(), {"selector": "x", "selector_type": "aria"}, _id)


def test_missing_selector_raises() -> None:
    with pytest.raises(ActionError):
        actions.click(MagicMock(), {}, _id)


def test_page_actions_table_is_complete() -> None:
    expected = {
        "navigate",
        "back",
        "forward",
        "reload",
        "click",
        "fill",
        "type",
        "press",
        "select",
        "hover",
        "scroll",
        "upload",
        "drag",
    }
    assert expected <= set(actions.PAGE_ACTIONS)
