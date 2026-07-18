"""Tests for acts/oracle/driver.py — vision routing over the inherited Continuum dispatch.

Driven with fakes (a MagicMock browser session, a recording provider, a patched capture): no
browser, no network, no extra needed. What is asserted is the mapping capture -> locate ->
humanized coordinate action, the wait_for polling, the read semantics, and that selector-based
steps still flow through the inherited Continuum path untouched.
"""

from __future__ import annotations

from random import Random
from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts._cognition.provider import GroundResult
from aetherius.acts._perception import Perception
from aetherius.acts.oracle.driver import OracleDriver
from aetherius.core.blueprint.models import Blueprint, StepModel
from aetherius.core.errors import ActionError, CognitionError, StepTimeoutError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.events.sinks import NullSink
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.selector import Box

pytestmark = pytest.mark.unit

_BOX = Box(x=100.0, y=80.0, width=120.0, height=40.0)
_PERCEPTION = Perception(screenshot=b"png", viewport=(1280, 720))

# The 30-70% off-center band of _BOX, the region every humanized point must land in.
_BAND_X = (100.0 + 0.3 * 120.0, 100.0 + 0.7 * 120.0)
_BAND_Y = (80.0 + 0.3 * 40.0, 80.0 + 0.7 * 40.0)


class _FakeProvider:
    """Records locate/read calls; replays a scripted list of GroundResults (last one repeats)."""

    def __init__(self, results: list[GroundResult] | None = None, read_value: Any = None) -> None:
        self.locate_calls: list[str] = []
        self.read_calls: list[tuple[str, Any]] = []
        self._results = list(results or [GroundResult(box=_BOX, confidence=0.9)])
        self._read_value = read_value

    def locate(self, perception: Perception, description: str) -> GroundResult:
        self.locate_calls.append(description)
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]

    def read(
        self, perception: Perception, description: str, *, schema: dict[str, Any] | None = None
    ) -> Any:
        self.read_calls.append((description, schema))
        return self._read_value


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


def _driver(
    provider: _FakeProvider | None = None, human: MagicMock | None = None
) -> tuple[OracleDriver, MagicMock]:
    driver = OracleDriver()
    session = MagicMock()
    session.human = human
    driver._session = session
    driver._humanized = frozenset()
    driver._provider = provider or _FakeProvider()
    driver._rng = Random(42)
    return driver, session


def _ctx() -> RunContext:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "oracle",
            "steps": [{"action": "set", "value": "x"}],
        }
    )
    return RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})


def _bus(sink: _RecordingSink | None = None) -> EventBus:
    bus = EventBus()
    bus.register(sink or NullSink())
    return bus


def _render(value: Any) -> Any:
    return value


def _run(
    driver: OracleDriver, step: dict[str, Any], *, bus: EventBus | None = None
) -> dict[str, Any]:
    return driver.run_step(StepModel.model_validate(step), _ctx(), bus or _bus(), _render)


@pytest.fixture(autouse=True)
def _fake_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aetherius.acts.oracle.driver.capture", lambda page: _PERCEPTION)


# ── Vision-targeted interactions ─────────────────────────────────────────────


def test_click_vision_grounds_then_clicks_offcenter() -> None:
    provider = _FakeProvider()
    human = MagicMock()
    driver, _ = _driver(provider, human=human)

    result = _run(driver, {"action": "click", "target": {"vision": "the Go button"}})

    assert result == {}
    assert provider.locate_calls == ["the Go button"]
    (x, y), _kwargs = human.click_at.call_args
    assert _BAND_X[0] <= x <= _BAND_X[1]
    assert _BAND_Y[0] <= y <= _BAND_Y[1]


def test_type_vision_types_at_the_grounded_point() -> None:
    human = MagicMock()
    driver, _ = _driver(human=human)

    _run(driver, {"action": "type", "target": {"vision": "the caption box"}, "text": "hello"})

    (x, y, text), _kwargs = human.type_at.call_args
    assert text == "hello"
    assert _BAND_X[0] <= x <= _BAND_X[1]


def test_hover_vision_moves_to_the_grounded_point() -> None:
    human = MagicMock()
    driver, _ = _driver(human=human)

    _run(driver, {"action": "hover", "target": {"vision": "the menu"}})

    human.hover_at.assert_called_once()


def test_upload_vision_feeds_the_file_chooser_opened_by_the_click() -> None:
    human = MagicMock()
    driver, session = _driver(human=human)

    _run(driver, {"action": "upload", "target": {"vision": "the dropzone"}, "file": "/v.mp4"})

    human.click_at.assert_called_once()
    chooser = session.page.expect_file_chooser.return_value.__enter__.return_value
    chooser.value.set_files.assert_called_once_with("/v.mp4")


def test_upload_vision_requires_a_file() -> None:
    driver, _ = _driver(human=MagicMock())
    with pytest.raises(ActionError, match="file"):
        _run(driver, {"action": "upload", "target": {"vision": "the dropzone"}})


def test_click_vision_with_stealth_off_degrades_to_raw_mouse() -> None:
    # No HumanInput on the session (stealth off): the driver builds a plain facade whose
    # click_at falls back to page.mouse.click.
    driver, session = _driver(human=None)

    _run(driver, {"action": "click", "target": {"vision": "the button"}})

    session.page.mouse.click.assert_called_once()


def test_grounding_emits_a_debug_progress_event_with_the_box() -> None:
    driver, _ = _driver(human=MagicMock())
    sink = _RecordingSink()

    _run(
        driver, {"id": "s1", "action": "click", "target": {"vision": "the button"}}, bus=_bus(sink)
    )

    events = [e for e in sink.events if e.type is EventType.PROGRESS]
    assert len(events) == 1
    assert events[0].step_id == "s1"
    assert events[0].data["box"] == {"x": 100.0, "y": 80.0, "width": 120.0, "height": 40.0}


def test_low_confidence_grounding_fails_the_step() -> None:
    driver, _ = _driver(_FakeProvider([GroundResult(box=_BOX, confidence=0.3)]))
    with pytest.raises(CognitionError, match="not confident"):
        _run(driver, {"action": "click", "target": {"vision": "a ghost"}})


def test_min_confidence_param_overrides_the_floor() -> None:
    driver, _ = _driver(_FakeProvider([GroundResult(box=_BOX, confidence=0.3)]), human=MagicMock())
    result = _run(
        driver,
        {"action": "click", "target": {"vision": "a faint element"}, "min_confidence": 0.2},
    )
    assert result == {}


def test_ambiguous_target_is_rejected() -> None:
    driver, _ = _driver(human=MagicMock())
    with pytest.raises(ActionError, match="Ambiguous"):
        _run(driver, {"action": "click", "selector": "#x", "target": {"vision": "y"}})


# ── wait_for by vision ───────────────────────────────────────────────────────


def test_wait_for_vision_polls_until_confident(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("aetherius.acts.oracle.driver.time.sleep", lambda s: sleeps.append(s))
    provider = _FakeProvider(
        [
            GroundResult(box=_BOX, confidence=0.1),
            GroundResult(box=_BOX, confidence=0.2),
            GroundResult(box=_BOX, confidence=0.95),
        ]
    )
    driver, _ = _driver(provider)

    result = _run(
        driver, {"action": "wait_for", "target": {"vision": "the toast"}, "timeout_ms": 60000}
    )

    assert result == {}
    assert provider.locate_calls == ["the toast"] * 3
    assert len(sleeps) == 2


def test_wait_for_vision_timeout_honours_the_failure_code() -> None:
    driver, _ = _driver(_FakeProvider([GroundResult(box=_BOX, confidence=0.1)]))

    with pytest.raises(StepTimeoutError) as exc_info:
        _run(
            driver,
            {
                "action": "wait_for",
                "target": {"vision": "the toast"},
                "timeout_ms": 0,
                "on_timeout": "fail:NO_TOAST",
            },
        )

    assert exc_info.value.code == "NO_TOAST"


# ── Semantic extraction (read) ───────────────────────────────────────────────


def test_read_with_schema_exposes_the_fields_as_outputs() -> None:
    schema = {"type": "object", "properties": {"labels": {"type": "array"}}}
    provider = _FakeProvider(read_value={"labels": ["Username", "Password"]})
    driver, _ = _driver(provider)

    result = _run(driver, {"action": "read", "vision": "the form labels", "schema": schema})

    assert result == {"labels": ["Username", "Password"]}
    assert provider.read_calls == [("the form labels", schema)]


def test_read_without_schema_wraps_the_value_under_data() -> None:
    driver, _ = _driver(_FakeProvider(read_value="In stock"))
    result = _run(driver, {"action": "read", "vision": "the availability label"})
    assert result == {"data": "In stock"}


def test_read_requires_a_vision_description() -> None:
    driver, _ = _driver()
    with pytest.raises(ActionError, match="vision"):
        _run(driver, {"action": "read"})


def test_read_rejects_a_non_object_schema() -> None:
    driver, _ = _driver()
    with pytest.raises(ActionError, match="schema"):
        _run(driver, {"action": "read", "vision": "x", "schema": "not-an-object"})


# ── Inherited Continuum dispatch stays untouched ─────────────────────────────


def test_click_with_a_selector_delegates_to_continuum() -> None:
    provider = _FakeProvider()
    driver, session = _driver(provider)

    _run(driver, {"action": "click", "selector": "#go"})

    assert provider.locate_calls == []
    session.page.locator.assert_called_with("#go")


def test_wait_for_with_a_selector_delegates_to_continuum() -> None:
    provider = _FakeProvider()
    driver, session = _driver(provider)

    _run(driver, {"action": "wait_for", "selector": ".done"})

    assert provider.locate_calls == []
    session.page.locator.assert_called_with(".done")
