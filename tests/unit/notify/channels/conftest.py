"""Shared capture transport for channel tests: every send is mocked, no real network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest


class Capture:
    """httpx.MockTransport that records requests and answers with a configurable status."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status)

        return httpx.MockTransport(handler)

    @property
    def only(self) -> httpx.Request:
        (request,) = self.requests
        return request

    @property
    def payload(self) -> Any:
        return json.loads(self.only.content)


@pytest.fixture()
def capture() -> Capture:
    return Capture()
