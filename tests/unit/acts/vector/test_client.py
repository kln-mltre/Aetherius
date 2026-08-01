"""Tests for acts/vector/client.py — uses httpx.MockTransport."""

from __future__ import annotations

import sys

import httpx
import pytest

from aetherius.acts.vector.client import VectorClient
from aetherius.core.errors import DependencyError, StatusAssertionError

pytestmark = pytest.mark.unit


def _client_with(payload: object, status: int = 200) -> VectorClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    c = VectorClient()
    c._client = httpx.Client(transport=httpx.MockTransport(handler))
    c._retry_decorator = None
    return c


def test_get_returns_response() -> None:
    client = _client_with({"ok": True})
    resp = client.request("GET", "https://example.com/api")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    client.close()


def test_post_with_form() -> None:
    received: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["method"] = request.method
        received["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(200, json={"received": True})

    client = VectorClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    client._retry_decorator = None
    client.request("POST", "https://example.com/form", form={"key": "value"})
    assert received["method"] == "POST"
    client.close()


def test_expected_status_mismatch_raises() -> None:
    client = _client_with({"error": "forbidden"}, status=403)
    with pytest.raises(StatusAssertionError) as exc_info:
        client.request("GET", "https://example.com/protected", expected_status=200)
    assert exc_info.value.expected == 200
    assert exc_info.value.actual == 403
    client.close()


def test_both_json_and_form_raises() -> None:
    from aetherius.core.errors import ActionError

    client = _client_with({})
    with pytest.raises(ActionError, match="json.*form|form.*json"):
        client.request("POST", "https://example.com/", json={"a": 1}, form={"b": "2"})
    client.close()


def test_context_manager() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with VectorClient() as client:
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        client._retry_decorator = None
        resp = client.request("GET", "https://example.com/")
        assert resp.status_code == 200


def test_proxy_is_passed_to_httpx_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    real_client = httpx.Client

    def spy(**kwargs: object) -> httpx.Client:
        captured.update(kwargs)
        # Build a real, network-free client; MockTransport does not accept a proxy kwarg.
        return real_client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200)),
            timeout=kwargs.get("timeout"),
            follow_redirects=bool(kwargs.get("follow_redirects", True)),
        )

    monkeypatch.setattr(httpx, "Client", spy)
    client = VectorClient(proxy="http://user:pass@h:8080")
    assert captured.get("proxy") == "http://user:pass@h:8080"
    client.close()


def test_default_headers_are_sent_and_overridable() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={})

    client = VectorClient(
        default_headers={"User-Agent": "prof-ua", "Sec-CH-UA": '"Chromium";v="126"'}
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    client._retry_decorator = None
    # A default header is sent; an explicit request header wins regardless of case.
    client.request("GET", "https://example.com/", headers={"user-agent": "explicit"})
    assert seen["sec-ch-ua"] == '"Chromium";v="126"'
    assert seen["user-agent"] == "explicit"
    client.close()


def test_a_captured_cookie_is_sent_on_the_next_request() -> None:
    """A session captured by one step must reach the next one.

    Found by a milestone 3-C probe: the client builds its own ``httpx.Request`` (to keep header
    precedence explicit), and httpx only attaches cookies in ``build_request``. A form login
    therefore captured its session and never used it again. Guarded here and by the conformance
    case ``run-session-cookie-between-steps``.
    """
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200, json={}, headers={"Set-Cookie": "SESSION=abc123; Path=/"})

    client = VectorClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    client._retry_decorator = None
    client.request("GET", "https://example.com/login")
    client.request("GET", "https://example.com/me")
    # An explicit Cookie header keeps priority over the jar.
    client.request("GET", "https://example.com/me", headers={"Cookie": "SESSION=explicit"})

    assert seen == [None, "SESSION=abc123", "SESSION=explicit"]
    client.close()


def test_impersonation_without_extra_raises_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate the [network] extra being absent so the import fails deterministically.
    monkeypatch.setitem(sys.modules, "curl_cffi", None)
    with pytest.raises(DependencyError) as exc:
        VectorClient(impersonate="chrome")
    assert exc.value.extra == "network"
