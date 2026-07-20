"""Unit tests for the human-in-the-loop rendezvous (core/runtime/approvals.py).

Pure in-memory: a worker thread parks on a rendezvous while another thread resolves it, exactly as
the console/CLI/daemon surfaces do. No browser, no daemon.
"""

from __future__ import annotations

import threading
import time

import pytest

from aetherius.core.runtime.approvals import (
    ApprovalRegistry,
    ApprovalRequest,
    Decision,
)

pytestmark = pytest.mark.unit


def test_request_tokens_are_unique_and_bound_to_the_run() -> None:
    a = ApprovalRequest.create("run", "ok?")
    b = ApprovalRequest.create("run", "ok?")
    assert a.token != b.token
    assert a.run_id == "run" and a.message == "ok?"


def test_wait_blocks_then_resumes_when_resolved() -> None:
    registry = ApprovalRegistry()
    request = ApprovalRequest.create("run-1", "proceed?")
    rendezvous = registry.open(request)

    def surface() -> None:
        time.sleep(0.05)
        assert registry.resolve("run-1", request.token, Decision(True, decided_by="test"))

    threading.Thread(target=surface, daemon=True).start()
    decision = rendezvous.wait(2.0)
    assert decision is not None
    assert decision.approved is True
    assert decision.decided_by == "test"


def test_wait_returns_none_on_timeout() -> None:
    registry = ApprovalRegistry()
    rendezvous = registry.open(ApprovalRequest.create("run-2", "proceed?"))
    assert rendezvous.wait(0.05) is None


def test_resolve_rejects_unknown_run_and_bad_token() -> None:
    registry = ApprovalRegistry()
    request = ApprovalRequest.create("run-3", "proceed?")
    registry.open(request)
    assert registry.resolve("nope", request.token, Decision(True)) is False
    assert registry.resolve("run-3", "wrong-token", Decision(True)) is False
    assert registry.resolve("run-3", request.token, Decision(True)) is True


def test_first_decision_wins() -> None:
    registry = ApprovalRegistry()
    request = ApprovalRequest.create("run-4", "proceed?")
    rendezvous = registry.open(request)
    assert registry.resolve("run-4", request.token, Decision(True, decided_by="first"))
    # A late second decision (e.g. a notification tap after the console modal) is a no-op.
    registry.resolve("run-4", request.token, Decision(False, decided_by="second"))
    decision = rendezvous.wait(0.1)
    assert decision is not None and decision.decided_by == "first"


def test_pending_and_close_track_the_open_request() -> None:
    registry = ApprovalRegistry()
    request = ApprovalRequest.create("run-5", "proceed?")
    assert registry.pending("run-5") is None
    registry.open(request)
    assert registry.pending("run-5") == request
    registry.close(request)
    assert registry.pending("run-5") is None
    # After close, a decision for the stale token resolves nothing.
    assert registry.resolve("run-5", request.token, Decision(True)) is False


def test_base_registry_has_no_notification_callback() -> None:
    registry = ApprovalRegistry()
    assert registry.notification_data(ApprovalRequest.create("run-6", "ok?")) == {}
