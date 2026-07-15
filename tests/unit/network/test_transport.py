"""Tests for network/transport.py — httpx proxy kwargs, the SOCKS5 guard, and impersonation probe."""

from __future__ import annotations

import importlib.util

import pytest

from aetherius.core.errors import DependencyError
from aetherius.network.identity import NetworkIdentity
from aetherius.network.proxy import ProxySpec
from aetherius.network.transport import httpx_proxy_kwargs, impersonation_available

pytestmark = pytest.mark.unit


def test_no_proxy_yields_no_kwargs() -> None:
    assert httpx_proxy_kwargs(NetworkIdentity()) == {}


def test_http_proxy_yields_proxy_kwarg() -> None:
    identity = NetworkIdentity(proxy=ProxySpec("http", "h", 8080, "u", "p"))
    assert httpx_proxy_kwargs(identity) == {"proxy": "http://u:p@h:8080"}


def test_socks5_without_socksio_raises_dependency_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "socksio":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    identity = NetworkIdentity(proxy=ProxySpec("socks5", "h", 1080))
    with pytest.raises(DependencyError) as exc:
        httpx_proxy_kwargs(identity)
    assert exc.value.extra == "network"


def test_socks5_with_socksio_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: object())
    identity = NetworkIdentity(proxy=ProxySpec("socks5", "h", 1080))
    assert httpx_proxy_kwargs(identity) == {"proxy": "socks5://h:1080"}


def test_impersonation_available_reflects_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    assert impersonation_available() is False
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: object())
    assert impersonation_available() is True
