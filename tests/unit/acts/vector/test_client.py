"""Tests for acts/vector/client.py — uses httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from aetherius.acts.vector.client import VectorClient
from aetherius.core.errors import StatusAssertionError

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
