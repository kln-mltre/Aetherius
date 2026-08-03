"""Tests for acts/continuum/driver.py — step dispatch with a fake browser session.

No real browser: a MagicMock stands in for BrowserSession.page, so these run in the base CI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts.continuum.driver import ContinuumDriver
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import ActionError, StepTimeoutError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.events.sinks import NullSink
from aetherius.core.runtime.context import RunContext

pytestmark = pytest.mark.unit


def _ctx(bp: Blueprint) -> RunContext:
    return RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})


def _null_bus() -> EventBus:
    bus = EventBus()
    bus.register(NullSink())
    return bus


def _bp(steps: list[dict[str, Any]]) -> Blueprint:
    return Blueprint.model_validate(
        {"aetherius": "1.0", "name": "t", "act": "continuum", "steps": steps}
    )


def _driver_with_page() -> tuple[ContinuumDriver, MagicMock]:
    driver = ContinuumDriver()
    session = MagicMock()
    page = MagicMock()
    session.page = page
    driver._session = session
    return driver, page


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


def test_dispatch_navigate() -> None:
    driver, page = _driver_with_page()
    page.url = "https://x"
    page.goto.return_value.status = 200
    bp = _bp([{"action": "navigate", "url": "https://x"}])
    out = driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    page.goto.assert_called_once()
    assert out["status"] == 200


def test_dispatch_click_delegates_to_page_action() -> None:
    driver, page = _driver_with_page()
    bp = _bp([{"action": "click", "selector": "#b"}])
    driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    page.locator.assert_called_once_with("#b")


def test_dispatch_extract() -> None:
    driver, page = _driver_with_page()
    page.locator.return_value.first.inner_text.return_value = "Bob"
    bp = _bp([{"action": "extract", "outputs": {"n": {"selector": ".n", "as": "text"}}}])
    out = driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    assert out == {"n": "Bob"}


def test_dispatch_shared_emit_emits_event() -> None:
    driver, _ = _driver_with_page()
    bp = _bp([{"action": "emit", "event": "LOGIN_SUCCESS"}])
    bus = EventBus()
    sink = _CollectingSink()
    bus.register(sink)
    driver.run_step(bp.steps[0], _ctx(bp), bus, lambda v: v)
    assert any(e.message == "LOGIN_SUCCESS" for e in sink.events)


def test_dispatch_screenshot_writes_and_emits_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, page = _driver_with_page()
    monkeypatch.setattr("aetherius.acts.continuum.driver.run_dir", lambda run_id: tmp_path)
    bp = _bp([{"id": "shot", "action": "screenshot"}])
    bus = EventBus()
    sink = _CollectingSink()
    bus.register(sink)
    out = driver.run_step(bp.steps[0], _ctx(bp), bus, lambda v: v)
    assert out["path"].endswith("shot.png")
    page.screenshot.assert_called_once()
    assert any(e.type is EventType.ARTIFACT for e in sink.events)


def test_dispatch_routes_to_human_when_policy_humanizes() -> None:
    driver, page = _driver_with_page()
    driver._humanized = frozenset({"click"})
    human = driver._session.human  # MagicMock facade stands in for HumanInput
    human.page = page
    bp = _bp([{"action": "click", "selector": "#b"}])
    driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    human.click.assert_called_once()


def test_dispatch_stays_plain_when_no_human_facade() -> None:
    driver, page = _driver_with_page()
    driver._session.human = None  # e.g. fingerprint-only or stealth off
    driver._humanized = frozenset({"click"})
    bp = _bp([{"action": "click", "selector": "#b"}])
    driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    page.locator.assert_called_once_with("#b")


def test_wait_parks_the_cursor_when_humanized() -> None:
    driver, _ = _driver_with_page()
    human = driver._session.human  # MagicMock facade
    bp = _bp([{"action": "wait", "ms": 0}])
    driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    human.park.assert_called_once()


def test_dispatch_unsupported_action_raises() -> None:
    driver, _ = _driver_with_page()
    bp = _bp([{"action": "http.request", "url": "x"}])
    with pytest.raises(ActionError):
        driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)


def test_run_step_before_setup_raises() -> None:
    driver = ContinuumDriver()
    bp = _bp([{"action": "click", "selector": "#b"}])
    with pytest.raises(ActionError):
        driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)


def test_locator_timeout_becomes_a_typed_step_failure() -> None:
    """A selector that no longer matches is a clean failure, not an engine bug re-raised.

    Playwright raises a bare TimeoutError; without translation the engine wraps it in a RunError and
    re-raises, so the most common Act II failure — a page that changed — reaches the caller as
    "something unexpected happened". The embedded engine reports it cleanly, and the two must agree
    (jalon 3-E, docs/embedded.md).
    """
    driver, page = _driver_with_page()
    page.locator.return_value.click.side_effect = TimeoutError("Locator.click: Timeout 30000ms")
    bp = _bp([{"action": "click", "selector": "#absent"}])

    with pytest.raises(StepTimeoutError) as excinfo:
        driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
    assert "never matched what the Blueprint expects" in str(excinfo.value)
    assert excinfo.value.code is None


def test_a_non_timeout_failure_keeps_its_own_path() -> None:
    # Translating everything would hide a real defect behind a reassuring message.
    driver, page = _driver_with_page()
    page.locator.return_value.click.side_effect = ValueError("something else entirely")
    bp = _bp([{"action": "click", "selector": "#b"}])

    with pytest.raises(ValueError):
        driver.run_step(bp.steps[0], _ctx(bp), _null_bus(), lambda v: v)
