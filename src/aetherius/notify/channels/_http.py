"""Shared delivery primitive: one JSON POST per notification, with a bounded timeout.

Every built-in channel is a JSON POST at heart; centralising the client construction keeps the
timeout and status discipline identical across channels.
"""

from __future__ import annotations

from typing import Any

import httpx

# A notification is a courtesy signal, never worth stalling the run it observes: keep the budget
# tight and independent from the Blueprint's own timeout options.
_TIMEOUT_S = 10.0


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """POST *payload* as JSON to *url*, raising on any non-2xx response.

    ``transport`` exists for tests (``httpx.MockTransport``); ``None`` means the real network.
    The raised error is contained by ``aetherius.notify.dispatch``, never by the channel itself.
    """
    with httpx.Client(timeout=_TIMEOUT_S, transport=transport) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
