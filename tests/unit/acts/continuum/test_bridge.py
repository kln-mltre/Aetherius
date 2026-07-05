"""Tests for acts/continuum/bridge.py — DOM extraction, wait_for and evaluate.

Fake page via unittest.mock; no browser needed (runs in base CI).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts.continuum import bridge
from aetherius.core.errors import ActionError, StepTimeoutError

pytestmark = pytest.mark.unit


def _id(value: Any) -> Any:
    return value


def test_extract_text_is_stripped() -> None:
    page = MagicMock()
    page.locator.return_value.first.inner_text.return_value = "  Bob  "
    out = bridge.extract(page, {"outputs": {"name": {"selector": ".n", "as": "text"}}}, _id)
    assert out == {"name": "Bob"}


def test_extract_number_from_noisy_text() -> None:
    page = MagicMock()
    page.locator.return_value.first.inner_text.return_value = "12 messages"
    out = bridge.extract(page, {"outputs": {"unread": {"selector": ".c", "as": "number"}}}, _id)
    assert out == {"unread": 12}


def test_extract_number_float_with_comma() -> None:
    page = MagicMock()
    page.locator.return_value.first.inner_text.return_value = "Total: 3,5"
    out = bridge.extract(page, {"outputs": {"v": {"selector": ".c", "as": "number"}}}, _id)
    assert out == {"v": 3.5}


def test_extract_attr_reads_attribute() -> None:
    page = MagicMock()
    page.locator.return_value.first.get_attribute.return_value = "https://x"
    out = bridge.extract(
        page, {"outputs": {"href": {"selector": "a", "as": "attr", "attr": "href"}}}, _id
    )
    assert out == {"href": "https://x"}
    page.locator.return_value.first.get_attribute.assert_called_once_with("href")


def test_extract_attr_without_name_raises() -> None:
    with pytest.raises(ActionError):
        bridge.extract(MagicMock(), {"outputs": {"x": {"selector": ".a", "as": "attr"}}}, _id)


def test_extract_count() -> None:
    page = MagicMock()
    page.locator.return_value.count.return_value = 4
    out = bridge.extract(page, {"outputs": {"n": {"selector": ".item", "as": "count"}}}, _id)
    assert out == {"n": 4}


def test_extract_unknown_type_raises() -> None:
    page = MagicMock()
    page.locator.return_value.first.inner_text.return_value = "x"
    with pytest.raises(ActionError):
        bridge.extract(page, {"outputs": {"x": {"selector": ".a", "as": "json"}}}, _id)


def test_extract_missing_selector_raises() -> None:
    with pytest.raises(ActionError):
        bridge.extract(MagicMock(), {"outputs": {"x": {"as": "text"}}}, _id)


def test_wait_for_success() -> None:
    page = MagicMock()
    out = bridge.wait_for(page, {"selector": ".ok", "timeout_ms": 5000}, _id)
    assert out == {}
    page.locator.assert_called_once_with(".ok")
    page.locator.return_value.wait_for.assert_called_once_with(state="visible", timeout=5000.0)


def test_wait_for_timeout_raises_with_failure_code() -> None:
    page = MagicMock()
    page.locator.return_value.wait_for.side_effect = TimeoutError("boom")
    with pytest.raises(StepTimeoutError) as excinfo:
        bridge.wait_for(page, {"selector": ".x", "on_timeout": "fail:LOGIN_FAILED"}, _id)
    assert excinfo.value.code == "LOGIN_FAILED"


def test_wait_for_non_timeout_error_propagates() -> None:
    page = MagicMock()
    page.locator.return_value.wait_for.side_effect = ValueError("other")
    with pytest.raises(ValueError):
        bridge.wait_for(page, {"selector": ".x"}, _id)


def test_evaluate_returns_result() -> None:
    page = MagicMock()
    page.evaluate.return_value = 42
    out = bridge.evaluate(page, {"script": "1+1"}, _id)
    assert out == {"result": 42}
    page.evaluate.assert_called_once_with("1+1")


def test_evaluate_with_arg() -> None:
    page = MagicMock()
    page.evaluate.return_value = "ok"
    bridge.evaluate(page, {"script": "a => a", "arg": 5}, _id)
    page.evaluate.assert_called_once_with("a => a", 5)


def test_evaluate_requires_script() -> None:
    with pytest.raises(ActionError):
        bridge.evaluate(MagicMock(), {}, _id)
