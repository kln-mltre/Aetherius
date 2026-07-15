"""Tests for network/identity.py — resolving options.proxy (and the environment default) into a
NetworkIdentity."""

from __future__ import annotations

import pytest

from aetherius.config import settings as settings_mod
from aetherius.core.errors import BlueprintValidationError
from aetherius.network.identity import NetworkIdentity, resolve_identity

pytestmark = pytest.mark.unit


def test_none_without_default_is_empty() -> None:
    assert resolve_identity(None) == NetworkIdentity()


def test_string_url_becomes_a_proxy() -> None:
    identity = resolve_identity("http://user:pass@h:8080")
    assert identity.proxy is not None
    assert identity.proxy.scheme == "http"
    assert identity.proxy.host == "h"
    assert identity.geo is None
    assert identity.impersonate is None


def test_object_with_pool_geo_and_impersonation() -> None:
    identity = resolve_identity(
        {
            "pool": ["socks5://a:1080", "socks5://b:1080"],
            "rotate": "sticky",
            "geo": "FR",
            "impersonate": True,
        },
        run_key="bp",
    )
    assert identity.proxy is not None and identity.proxy.host in {"a", "b"}
    assert identity.geo is not None and identity.geo.timezone_id == "Europe/Paris"
    assert identity.impersonate == "chrome"  # True normalises to "chrome"


def test_impersonate_string_is_kept() -> None:
    assert resolve_identity({"url": "http://h:1", "impersonate": "safari"}).impersonate == "safari"


def test_object_without_url_or_pool_is_rejected() -> None:
    with pytest.raises(BlueprintValidationError, match="url.*pool|pool.*url"):
        resolve_identity({"geo": "FR"})


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(BlueprintValidationError, match="Unknown"):
        resolve_identity({"url": "http://h:1", "rotten": True})


def test_non_mapping_option_is_rejected() -> None:
    with pytest.raises(BlueprintValidationError, match="string.*object|url"):
        resolve_identity(42)


def test_sticky_key_is_stable_across_calls() -> None:
    option = {"pool": ["http://a:1", "http://b:2", "http://c:3"], "rotate": "sticky"}
    first = resolve_identity(option, run_key="same").proxy
    second = resolve_identity(option, run_key="same").proxy
    assert first == second


def test_environment_default_is_used_when_no_option(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHERIUS_PROXY_URL", "http://default:3128")
    settings_mod.get_settings.cache_clear()
    try:
        identity = resolve_identity(None)
        assert identity.proxy is not None
        assert identity.proxy.host == "default"
        assert identity.proxy.port == 3128
    finally:
        settings_mod.get_settings.cache_clear()


def test_blueprint_option_wins_over_environment_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHERIUS_PROXY_URL", "http://default:3128")
    settings_mod.get_settings.cache_clear()
    try:
        identity = resolve_identity("http://explicit:9000")
        assert identity.proxy is not None and identity.proxy.host == "explicit"
    finally:
        settings_mod.get_settings.cache_clear()
