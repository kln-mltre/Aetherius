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


def _text_locator(value: str) -> MagicMock:
    locator = MagicMock()
    locator.inner_text.return_value = value
    return locator


def test_extract_list_reads_every_match() -> None:
    page = MagicMock()
    page.locator.return_value.all.return_value = [_text_locator("One"), _text_locator("Two")]
    out = bridge.extract(page, {"outputs": {"titles": {"selector": ".t", "as": "list"}}}, _id)
    assert out == {"titles": ["One", "Two"]}


def test_extract_list_with_number_items() -> None:
    page = MagicMock()
    page.locator.return_value.all.return_value = [_text_locator("$3"), _text_locator("$4,5")]
    out = bridge.extract(
        page,
        {"outputs": {"prices": {"selector": ".p", "as": "list", "item": "number"}}},
        _id,
    )
    assert out == {"prices": [3, 4.5]}


def _record_container(mapping: dict[str, str]) -> MagicMock:
    """A fake container whose .locator(sel).first.inner_text returns per-selector text."""
    container = MagicMock()

    def locate(selector: str) -> MagicMock:
        holder = MagicMock()
        holder.first.inner_text.return_value = mapping[selector]
        return holder

    container.locator.side_effect = locate
    return container


def test_extract_records_reads_fields_per_container() -> None:
    page = MagicMock()
    page.locator.return_value.all.return_value = [
        _record_container({".title": "A", ".author": "X"}),
        _record_container({".title": "B", ".author": "Y"}),
    ]
    spec = {
        "outputs": {
            "quotes": {
                "each": ".quote",
                "fields": {
                    "text": {"selector": ".title", "as": "text"},
                    "author": {"selector": ".author", "as": "text"},
                },
            }
        }
    }
    out = bridge.extract(page, spec, _id)
    assert out == {"quotes": [{"text": "A", "author": "X"}, {"text": "B", "author": "Y"}]}
    page.locator.assert_any_call(".quote")


def test_extract_records_without_fields_raises() -> None:
    page = MagicMock()
    with pytest.raises(ActionError):
        bridge.extract(page, {"outputs": {"x": {"each": ".row", "fields": {}}}}, _id)


def test_wait_for_success_waits_on_first_match() -> None:
    # `.first` avoids Playwright strict-mode errors when the selector matches several elements.
    page = MagicMock()
    out = bridge.wait_for(page, {"selector": ".ok", "timeout_ms": 5000}, _id)
    assert out == {}
    page.locator.assert_called_once_with(".ok")
    page.locator.return_value.first.wait_for.assert_called_once_with(
        state="visible", timeout=5000.0
    )


def test_wait_for_timeout_raises_with_failure_code() -> None:
    page = MagicMock()
    page.locator.return_value.first.wait_for.side_effect = TimeoutError("boom")
    with pytest.raises(StepTimeoutError) as excinfo:
        bridge.wait_for(page, {"selector": ".x", "on_timeout": "fail:LOGIN_FAILED"}, _id)
    assert excinfo.value.code == "LOGIN_FAILED"


def test_wait_for_non_timeout_error_propagates() -> None:
    page = MagicMock()
    page.locator.return_value.first.wait_for.side_effect = ValueError("other")
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
