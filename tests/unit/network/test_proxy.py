"""Tests for network/proxy.py — parsing and per-engine rendering of a proxy endpoint."""

from __future__ import annotations

import pytest

from aetherius.core.errors import BlueprintValidationError
from aetherius.network.proxy import ProxySpec, parse_proxy

pytestmark = pytest.mark.unit


def test_parse_plain_http() -> None:
    spec = parse_proxy("http://1.2.3.4:8080")
    assert spec == ProxySpec("http", "1.2.3.4", 8080)


def test_parse_with_credentials_decodes_userinfo() -> None:
    spec = parse_proxy("socks5://user:p%40ss@host.example:1080")
    assert spec.scheme == "socks5"
    assert spec.host == "host.example"
    assert spec.port == 1080
    assert spec.username == "user"
    assert spec.password == "p@ss"  # %40 decoded


@pytest.mark.parametrize("url", ["ftp://h:21", "gopher://h:70"])
def test_parse_rejects_unknown_scheme(url: str) -> None:
    with pytest.raises(BlueprintValidationError, match="scheme"):
        parse_proxy(url)


def test_parse_requires_a_port() -> None:
    with pytest.raises(BlueprintValidationError, match="port"):
        parse_proxy("http://host.example")


def test_parse_requires_a_host() -> None:
    with pytest.raises(BlueprintValidationError, match="host"):
        parse_proxy("http://:8080")


def test_for_httpx_inlines_and_encodes_credentials() -> None:
    spec = ProxySpec("http", "h", 8080, "user", "p@ss")
    # The '@' in the password is percent-encoded so it cannot corrupt the URL.
    assert spec.for_httpx() == "http://user:p%40ss@h:8080"


def test_for_httpx_without_credentials_is_the_server_url() -> None:
    assert ProxySpec("http", "h", 8080).for_httpx() == "http://h:8080"


def test_for_playwright_splits_credentials() -> None:
    spec = ProxySpec("socks5", "h", 1080, "user", "pass")
    assert spec.for_playwright() == {
        "server": "socks5://h:1080",
        "username": "user",
        "password": "pass",
    }


def test_for_playwright_omits_absent_credentials() -> None:
    assert ProxySpec("http", "h", 8080).for_playwright() == {"server": "http://h:8080"}


def test_redacted_hides_credentials() -> None:
    redacted = ProxySpec("http", "h", 8080, "user", "secret").redacted()
    assert "user" not in redacted
    assert "secret" not in redacted
    assert "***" in redacted
