"""Tests for server/config.py — daemon configuration and environment resolution."""

from __future__ import annotations

import pytest

from aetherius.server.config import DaemonConfig

pytestmark = pytest.mark.unit


def test_defaults_bind_loopback() -> None:
    config = DaemonConfig()

    assert config.host == "127.0.0.1"
    assert config.port == 8787
    assert config.token is None
    assert config.base_url == "http://127.0.0.1:8787"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHERIUS_DAEMON_HOST", "0.0.0.0")
    monkeypatch.setenv("AETHERIUS_DAEMON_PORT", "9999")
    monkeypatch.setenv("AETHERIUS_DAEMON_TOKEN", "sekret")

    config = DaemonConfig()

    assert config.host == "0.0.0.0"
    assert config.port == 9999
    assert config.token == "sekret"
    assert config.base_url == "http://0.0.0.0:9999"
