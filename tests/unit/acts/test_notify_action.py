"""End-to-end tests for the notify action through RunEngine (Vector driver).

A recording channel kind is registered for the duration of each test — dogfooding the plugin seam —
so the full path (template rendering, target folding, build_channel, dispatch, PROGRESS event) is
exercised without any network. Continuum shares the exact same mixin handler; its wiring is covered
by tests/unit/acts/test_action_dispatch.py.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.engine import RunEngine
from aetherius.core.runtime.result import Result, RunStatus
from aetherius.notify import Notification, NotificationChannel
from aetherius.notify import registry

pytestmark = pytest.mark.unit


class FakeChannel:
    def __init__(self) -> None:
        self.configs: list[dict[str, str]] = []
        self.sent: list[Notification] = []
        self.explode = False

    def send(self, notification: Notification) -> None:
        if self.explode:
            raise RuntimeError("provider down")
        self.sent.append(notification)


class ListSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


@pytest.fixture()
def fake_channel() -> Iterator[FakeChannel]:
    channel = FakeChannel()

    @registry.register_channel("fake", target_key="address")
    def _build(config: Mapping[str, str]) -> NotificationChannel:
        channel.configs.append(dict(config))
        return channel

    try:
        yield channel
    finally:
        registry._channels.pop("fake", None)
        registry._target_keys.pop("fake", None)


def _run(step: dict[str, Any], **inputs: Any) -> tuple[Result, ListSink]:
    blueprint = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t.notify",
            "act": "vector",
            "inputs": {"product": {"type": "string", "required": False, "default": "Widget"}},
            "steps": [step],
        }
    )
    sink = ListSink()
    result = RunEngine().run(blueprint, inputs=inputs, sinks=[sink])
    return result, sink


def test_notify_renders_and_delivers(fake_channel: FakeChannel) -> None:
    result, sink = _run(
        {
            "id": "alert",
            "action": "notify",
            "channel": "fake",
            "target": "room-7",
            "title": "Restock",
            "message": "Back in stock: {{ inputs.product }}",
            "level": "warning",
            "url": "https://shop.example/p",
        }
    )
    assert result.status is RunStatus.SUCCESS
    assert result.step_results[0].outputs == {"delivered": True, "channel": "fake"}
    assert fake_channel.configs == [{"address": "room-7"}]
    (notification,) = fake_channel.sent
    assert notification.body == "Back in stock: Widget"
    assert notification.title == "Restock"
    assert notification.level.value == "warning"
    assert notification.url == "https://shop.example/p"
    assert any(
        e.type is EventType.PROGRESS and e.message == "notify: fake delivered" for e in sink.events
    )


def test_config_object_feeds_multi_key_channels(fake_channel: FakeChannel) -> None:
    result, _ = _run(
        {
            "action": "notify",
            "channel": "fake",
            "message": "ping",
            "config": {"address": "room-7", "token": "{{ inputs.product }}"},
        }
    )
    assert result.status is RunStatus.SUCCESS
    assert fake_channel.configs == [{"address": "room-7", "token": "Widget"}]


def test_when_guard_skips_the_alert(fake_channel: FakeChannel) -> None:
    result, sink = _run(
        {
            "id": "alert",
            "action": "notify",
            "when": "{{ 1 == 2 }}",
            "channel": "fake",
            "target": "room-7",
            "message": "ping",
        }
    )
    assert result.status is RunStatus.SUCCESS
    assert result.step_results[0].status is RunStatus.SKIPPED
    assert fake_channel.sent == []
    assert any(e.type is EventType.STEP_SKIPPED for e in sink.events)


def test_unknown_channel_fails_the_step(fake_channel: FakeChannel) -> None:
    result, _ = _run({"action": "notify", "channel": "nope", "message": "ping"})
    assert result.status is RunStatus.FAILED
    assert result.error is not None and "Unknown notification channel" in result.error


def test_invalid_level_fails_the_step(fake_channel: FakeChannel) -> None:
    result, _ = _run(
        {"action": "notify", "channel": "fake", "target": "x", "message": "p", "level": "loud"}
    )
    assert result.status is RunStatus.FAILED
    assert result.error is not None and "invalid level" in result.error


def test_delivery_failure_is_contained_and_reported(fake_channel: FakeChannel) -> None:
    fake_channel.explode = True
    result, sink = _run(
        {"id": "alert", "action": "notify", "channel": "fake", "target": "x", "message": "ping"}
    )
    assert result.status is RunStatus.SUCCESS
    assert result.step_results[0].outputs == {"delivered": False, "channel": "fake"}
    assert any(
        e.type is EventType.PROGRESS
        and e.message == "notify: fake delivery failed"
        and e.level == "warning"
        for e in sink.events
    )
