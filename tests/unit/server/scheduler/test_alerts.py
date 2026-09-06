"""Tests for scheduler/alerts.py — the per-schedule notify policy and its change dedup."""

from __future__ import annotations

from typing import Any, Iterator, Mapping

import pytest

from aetherius.core.errors import ScheduleError
from aetherius.notify import Notification, registry
from aetherius.server.scheduler import apply_notify_policy, validate_notify_policy
from aetherius.store import Store

from .conftest import make_schedule

pytestmark = pytest.mark.unit


class CaptureChannel:
    """Records notifications instead of delivering them."""

    def __init__(self) -> None:
        self.sent: list[Notification] = []
        self.configs: list[Mapping[str, str]] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> Iterator[CaptureChannel]:
    """A 'capture' channel kind registered for the duration of one test."""
    channel = CaptureChannel()

    def factory(config: Mapping[str, str]) -> CaptureChannel:
        channel.configs.append(dict(config))
        return channel

    monkeypatch.setitem(registry._channels, "capture", factory)
    monkeypatch.setitem(registry._target_keys, "capture", "target")
    yield channel


def _policy(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"channel": "capture"}
    base.update(overrides)
    return base


def _apply(store: Store, notify: dict[str, Any], **kwargs: Any) -> bool | None:
    record = make_schedule(notify=notify)
    call: dict[str, Any] = {
        "status": "success",
        "error": None,
        "outputs": {},
        "secrets": {},
        "store": store,
    }
    call.update(kwargs)
    return apply_notify_policy(record, **call)


# ── validate_notify_policy ────────────────────────────────────────────────────


def test_validate_accepts_an_empty_policy() -> None:
    validate_notify_policy({})


def test_validate_accepts_a_builtin_channel() -> None:
    validate_notify_policy({"channel": "webhook", "target": "https://example.test/hook"})


def test_validate_rejects_a_missing_channel() -> None:
    with pytest.raises(ScheduleError, match="channel"):
        validate_notify_policy({"on": "always"})


def test_validate_rejects_an_unknown_channel() -> None:
    with pytest.raises(ScheduleError, match="Unknown notification channel"):
        validate_notify_policy({"channel": "carrier-pigeon"})


def test_validate_rejects_an_unknown_on_value() -> None:
    with pytest.raises(ScheduleError, match="'on'"):
        validate_notify_policy({"channel": "webhook", "on": "sometimes"})


def test_validate_rejects_a_non_object_config() -> None:
    with pytest.raises(ScheduleError, match="config"):
        validate_notify_policy({"channel": "webhook", "config": "not-a-dict"})


# ── apply_notify_policy ───────────────────────────────────────────────────────


def test_no_policy_sends_nothing(store: Store) -> None:
    assert _apply(store, {}, status="failed") is None


def test_failure_policy_alerts_only_on_failure(store: Store, capture: CaptureChannel) -> None:
    assert _apply(store, _policy(), status="failed", error="boom") is True
    assert _apply(store, _policy(), status="success") is None

    assert len(capture.sent) == 1
    assert capture.sent[0].level.value == "error"
    assert "boom" in capture.sent[0].body


def test_success_policy_alerts_only_on_success(store: Store, capture: CaptureChannel) -> None:
    assert _apply(store, _policy(on="success"), status="success") is True
    assert _apply(store, _policy(on="success"), status="failed") is None


def test_always_policy_alerts_on_both(store: Store, capture: CaptureChannel) -> None:
    assert _apply(store, _policy(on="always"), status="success") is True
    assert _apply(store, _policy(on="always"), status="failed") is True


def test_partial_is_not_a_failure(store: Store, capture: CaptureChannel) -> None:
    # Jalon 3-J: a partial run delivered the readings that did arrive. Waking someone for it would
    # make the failure alert mean nothing — so `failure` stays silent and `success` fires.
    assert _apply(store, _policy(), status="partial") is None
    assert _apply(store, _policy(on="success"), status="partial") is True


def test_partial_never_moves_the_change_baseline(store: Store, capture: CaptureChannel) -> None:
    # Incomplete outputs are not a reference: adopting them would make the next *complete* run
    # look like a change. Same reason a failure does not move it.
    policy = _policy(on="change")

    assert _apply(store, policy, outputs={"in_stock": False}) is True  # first observation
    assert _apply(store, policy, status="partial", outputs={"in_stock": True}) is None
    assert _apply(store, policy, outputs={"in_stock": False}) is None  # baseline untouched


def test_change_policy_alerts_only_on_transition(store: Store, capture: CaptureChannel) -> None:
    policy = _policy(on="change")

    assert _apply(store, policy, outputs={"in_stock": False}) is True  # first observation
    assert _apply(store, policy, outputs={"in_stock": False}) is None  # same state: silent
    assert _apply(store, policy, outputs={"in_stock": True}) is True  # transition: alert

    assert len(capture.sent) == 2


def test_change_policy_ignores_failures_and_keeps_the_baseline(
    store: Store, capture: CaptureChannel
) -> None:
    policy = _policy(on="change")
    assert _apply(store, policy, outputs={"in_stock": False}) is True

    # A transient failure neither alerts nor moves the baseline...
    assert _apply(store, policy, status="failed", outputs={}) is None
    # ...so the next identical success is still recognized as "no change".
    assert _apply(store, policy, outputs={"in_stock": False}) is None


def test_target_and_config_render_secret_references(store: Store, capture: CaptureChannel) -> None:
    policy = _policy(target="{{ secrets.hook }}", config={"extra": "{{ secrets.extra }}"})

    delivered = _apply(
        store,
        policy,
        status="failed",
        secrets={"hook": "https://hook.test", "extra": "v"},
    )

    assert delivered is True
    assert capture.configs == [{"target": "https://hook.test", "extra": "v"}]


def test_notification_carries_the_schedule_identity(store: Store, capture: CaptureChannel) -> None:
    _apply(store, _policy(on="always"), outputs={"quote": "x"})

    notification = capture.sent[0]
    assert "watch" in (notification.title or "")
    assert notification.data["schedule_id"] == "sch-1"


def test_a_broken_channel_config_is_contained(store: Store) -> None:
    # 'nope' bypassed write-time validation (e.g. a plugin channel no longer installed): the alert
    # is dropped and reported as failed, never raised into the tick loop.
    assert _apply(store, {"channel": "nope"}, status="failed") is False


def test_an_unresolvable_secret_is_contained(store: Store, capture: CaptureChannel) -> None:
    policy = _policy(target="{{ secrets.missing }}")

    assert _apply(store, policy, status="failed", secrets={}) is False
    assert capture.sent == []


def test_a_delivery_failure_is_contained(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    class ExplodingChannel:
        def send(self, notification: Notification) -> None:
            raise ConnectionError("wire down")

    monkeypatch.setitem(registry._channels, "capture", lambda config: ExplodingChannel())

    assert _apply(store, _policy(), status="failed") is False
