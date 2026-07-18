"""Tests for acts/vector/driver.py — uses httpx.MockTransport to avoid real network."""

from __future__ import annotations


import httpx
import pytest

from aetherius.acts.vector.client import VectorClient
from aetherius.acts.vector.driver import VectorDriver
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import ActionError, StatusAssertionError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.sinks import NullSink
from aetherius.core.runtime.context import RunContext

pytestmark = pytest.mark.unit

_EVENTS_PAYLOAD = [
    {
        "id": "1",
        "start": "2026-09-07T08:00",
        "eventCategory": "Cours",
        "backgroundColor": "#3b82f6",
    },
    {
        "id": "2",
        "start": "2026-09-07T10:00",
        "eventCategory": "Vacances",
        "backgroundColor": "#f00",
    },
]


def _make_transport(payload: object, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


def _make_ctx(blueprint: Blueprint) -> RunContext:
    return RunContext(
        run_id="test-run",
        blueprint=blueprint,
        inputs={},
        secrets={},
    )


def _make_bus() -> EventBus:
    bus = EventBus()
    bus.register(NullSink())
    return bus


@pytest.fixture
def simple_blueprint() -> Blueprint:
    return Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": "vector",
            "steps": [
                {
                    "id": "req",
                    "action": "http.request",
                    "method": "GET",
                    "url": "https://example.com/api",
                    "expect": {"status": 200},
                    "extract": {
                        "events": {
                            "from": "json",
                            "path": "$[*]",
                            "where": "item.eventCategory != 'Vacances'",
                        }
                    },
                }
            ],
            "outputs": {"events": "{{ steps.req.events }}"},
        }
    )


def test_http_request_extracts_filtered_events(simple_blueprint: Blueprint) -> None:
    driver = VectorDriver()
    ctx = _make_ctx(simple_blueprint)
    bus = _make_bus()

    # Inject mock transport into the client
    driver._client = VectorClient.__new__(VectorClient)
    driver._client._client = httpx.Client(transport=_make_transport(_EVENTS_PAYLOAD))
    driver._client._retries = simple_blueprint.options.retries
    driver._client._auth = __import__("aetherius.acts.vector.auth", fromlist=["NoAuth"]).NoAuth()
    driver._client._retry_decorator = None
    driver._client._impersonate_client = None
    driver._client._default_headers = {}

    step = simple_blueprint.steps[0]

    def renderer(v: object) -> object:
        return v

    result = driver.run_step(step, ctx, bus, renderer)
    assert result["status_code"] == 200
    assert len(result["events"]) == 1
    assert result["events"][0]["eventCategory"] == "Cours"


def test_assert_passes() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "vector",
            "steps": [{"action": "assert", "condition": "True"}],
        }
    )
    driver = VectorDriver()
    ctx = _make_ctx(bp)
    bus = _make_bus()
    step = bp.steps[0]
    result = driver.run_step(step, ctx, bus, lambda v: v)
    assert result == {}


def test_assert_fails() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "vector",
            "steps": [{"action": "assert", "condition": "False"}],
        }
    )
    driver = VectorDriver()
    ctx = _make_ctx(bp)
    bus = _make_bus()
    step = bp.steps[0]
    with pytest.raises(StatusAssertionError):
        driver.run_step(step, ctx, bus, lambda v: v)


def test_set_stores_value() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "vector",
            "steps": [{"action": "set", "value": "hello"}],
        }
    )
    driver = VectorDriver()
    ctx = _make_ctx(bp)
    bus = _make_bus()
    step = bp.steps[0]
    result = driver.run_step(step, ctx, bus, lambda v: v)
    assert result == {"value": "hello"}


def test_wait_executes_without_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []
    # `wait` is provided by the shared mixin; patch sleep where it is actually called.
    monkeypatch.setattr("aetherius.acts._shared.time.sleep", lambda s: calls.append(s))
    bp = Blueprint.model_validate(
        {"aetherius": "1.0", "name": "t", "act": "vector", "steps": [{"action": "wait", "ms": 100}]}
    )
    driver = VectorDriver()
    ctx = _make_ctx(bp)
    bus = _make_bus()
    step = bp.steps[0]
    driver.run_step(step, ctx, bus, lambda v: v)
    assert calls == [0.1]


def test_wait_draws_a_random_duration_from_a_range(monkeypatch: pytest.MonkeyPatch) -> None:
    # Without 'ms', the duration is drawn uniformly from [min_ms, max_ms] (stealth-style pauses).
    calls: list[float] = []
    monkeypatch.setattr("aetherius.acts._shared.time.sleep", lambda s: calls.append(s))
    monkeypatch.setattr("aetherius.acts._shared.random.uniform", lambda a, b: (a + b) / 2)
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "vector",
            "steps": [{"action": "wait", "min_ms": 100, "max_ms": 300}],
        }
    )
    driver = VectorDriver()
    driver.run_step(bp.steps[0], _make_ctx(bp), _make_bus(), lambda v: v)
    assert calls == [0.2]


def test_wait_rejects_an_inverted_range() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "vector",
            "steps": [{"action": "wait", "min_ms": 300, "max_ms": 100}],
        }
    )
    driver = VectorDriver()
    with pytest.raises(ActionError, match="max_ms"):
        driver.run_step(bp.steps[0], _make_ctx(bp), _make_bus(), lambda v: v)
