"""Vector recorder backend: turn captured API calls into an ``http.request`` Blueprint (Act I).

The in-page script (:mod:`._vector_js`) observes network calls and lets the user pick a request and
the JSON fields to extract; this backend transforms those picks into ``http.request`` steps with
JSONPath extraction (the shape [`acts/vector/driver.py`] runs). Picks on the same request coalesce
into one step. Auth-bearing headers become ``{{ secrets.x }}`` — never stored literally — the network
analogue of the DOM recorder's credentials→secrets.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote_plus

from ._names import ident, unique
from ._vector_js import VECTOR_JS
from .base import RecordingResult, register_backend
from .session import RecordingSession

# Header names (lowercased) that carry credentials: kept as secret placeholders, never in the file.
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "x-api-key", "api-key", "x-auth-token", "x-csrf-token"}
)


def _parse_body(body: str | None) -> tuple[str | None, Any]:
    """Classify a request body: JSON object/array, url-encoded form, or unknown (omitted)."""
    if not body:
        return None, None
    text = body.strip()
    if text[:1] in "{[":
        try:
            return "json", json.loads(text)
        except ValueError:
            pass
    if "=" in text:
        form: dict[str, str] = {}
        for pair in text.split("&"):
            key, _, value = pair.partition("=")
            form[unquote_plus(key)] = unquote_plus(value)
        return "form", form
    return None, None


def _clean_headers(raw: dict[str, Any], secrets: list[str]) -> dict[str, str]:
    """Keep Content-Type; turn auth headers into secret placeholders; drop browser noise."""
    clean: dict[str, str] = {}
    for name, value in raw.items():
        lowered = str(name).lower()
        if lowered in _SENSITIVE_HEADERS:
            secret = unique(ident(lowered.replace("-", "_"), fallback="token"), set(secrets))
            secrets.append(secret)
            clean[name] = f"{{{{ secrets.{secret} }}}}"
        elif lowered == "content-type":
            clean[name] = str(value)
    return clean


def _build_request_step(
    request_id: str, request: dict[str, Any], secrets: list[str]
) -> dict[str, Any]:
    """Reproduce a captured request as an http.request step (method/url/headers/body/expect)."""
    step: dict[str, Any] = {
        "id": request_id,
        "action": "http.request",
        "method": str(request.get("method", "GET")),
        "url": str(request.get("url", "")),
    }
    headers = _clean_headers(request.get("headers") or {}, secrets)
    if headers:
        step["headers"] = headers
    body_kind, body_value = _parse_body(request.get("body"))
    if body_kind == "json":
        step["json"] = body_value
    elif body_kind == "form":
        step["form"] = body_value
    step["expect"] = {"status": int(request.get("status") or 200)}
    return step


def _extract_spec(extract: dict[str, Any]) -> dict[str, Any]:
    """One extract entry: JSONPath, plus a fields map for records."""
    spec: dict[str, Any] = {"from": "json", "path": str(extract.get("path", "$"))}
    fields = extract.get("fields")
    if fields:
        spec["fields"] = {str(k): str(v) for k, v in fields.items()}
    return spec


def transform(events: list[dict[str, Any]]) -> RecordingResult:
    """Turn captured ``http_request`` picks into http.request steps, secrets and outputs."""
    steps: list[dict[str, Any]] = []
    secrets: list[str] = []
    outputs: dict[str, Any] = {}
    by_request: dict[tuple[str, str, str], dict[str, Any]] = {}
    output_names: set[str] = set()
    sequence = 0

    for event in events:
        request = event.get("request") or {}
        extract = event.get("extract") or {}
        key = (str(request.get("method")), str(request.get("url")), str(request.get("body")))
        step = by_request.get(key)
        if step is None:
            sequence += 1
            request_id = "req" if sequence == 1 else f"req_{sequence}"
            step = _build_request_step(request_id, request, secrets)
            by_request[key] = step
            steps.append(step)
        name = unique(ident(extract.get("name"), fallback="data"), output_names)
        output_names.add(name)
        step.setdefault("extract", {})[name] = _extract_spec(extract)
        outputs[name] = f"{{{{ steps.{step['id']}.{name} }}}}"

    return RecordingResult(steps=steps, secrets=secrets, inputs={}, outputs=outputs)


def _describe(event: dict[str, Any]) -> str:
    request = event.get("request") or {}
    return f"{request.get('method', 'GET')} {request.get('url', '')}  -> {event.get('extract', {}).get('name', '?')}"


class VectorRecorder:
    """Records API calls (via a browser) into a ``vector`` Blueprint."""

    act = "vector"

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._session: RecordingSession | None = None

    def init_scripts(self) -> list[str]:
        return [VECTOR_JS]

    def attach(self, session: RecordingSession) -> None:
        self._session = session
        session.expose("__aetherius_capture", self._on_binding)

    def result(self) -> RecordingResult:
        return transform(self._events)

    def _on_binding(self, _source: dict[str, Any], payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        if data.get("kind") == "finish":
            if self._session is not None:
                self._session.finish()
            return
        if data.get("kind") == "http_request":
            self._events.append(data)
            if self._session is not None:
                self._session.notify(_describe(data))


register_backend("vector", lambda **_: VectorRecorder())
