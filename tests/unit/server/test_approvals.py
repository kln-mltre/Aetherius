"""Tests for the daemon approval gateway's notification callback (server/approvals.py)."""

from __future__ import annotations

import pytest

from aetherius.core.runtime.approvals import ApprovalRequest
from aetherius.server.approvals import DaemonApprovalRegistry

pytestmark = pytest.mark.unit


def test_notification_data_is_empty_without_a_public_url() -> None:
    registry = DaemonApprovalRegistry(public_url=None, token="s3cr3t")
    assert registry.notification_data(ApprovalRequest.create("run", "ok?")) == {}


def test_notification_data_builds_the_decision_callback() -> None:
    registry = DaemonApprovalRegistry(public_url="https://box.example/", token="s3cr3t")
    request = ApprovalRequest.create("run-1", "ok?")
    data = registry.notification_data(request)
    confirm = data["confirm"]
    assert confirm["decisions_url"] == "https://box.example/v1/runs/run-1/decisions"
    assert confirm["token"] == request.token
    assert confirm["auth"] == "Bearer s3cr3t"


def test_notification_data_omits_auth_without_a_token() -> None:
    registry = DaemonApprovalRegistry(public_url="https://box.example", token=None)
    confirm = registry.notification_data(ApprovalRequest.create("run-2", "ok?"))["confirm"]
    assert "auth" not in confirm
