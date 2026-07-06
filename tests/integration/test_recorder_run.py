"""End-to-end recorder capture against a real Chromium.

The Blueprint recorder itself opens a *headed* browser for a human to drive, which cannot run in a
headless CI job. So these tests inject the very same capture scripts into a headless browser and
drive the demonstration with Playwright, exercising the real capture JS, descriptor parsing, selector
uniqueness (measured against a live DOM) and the transform to a validated Blueprint. The headed
launch/pump glue is thin and covered by the manual "Tester" flow in docs/recorder.md.

Marked ``browser``: skipped in the base CI (no [browser] extra), run by the dedicated browser job.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest

pytestmark = pytest.mark.browser
pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

from aetherius.core.blueprint.models import Blueprint  # noqa: E402
from aetherius.core.blueprint.validator import validate_for_act  # noqa: E402
from aetherius.recorder._capture_js import RECORDER_JS  # noqa: E402
from aetherius.recorder._gesture_js import GESTURE_RECORDER_JS  # noqa: E402
from aetherius.recorder.blueprint_recorder import assemble_blueprint, events_to_steps  # noqa: E402
from aetherius.recorder.capture import RecordedEvent, _descriptor_from_raw  # noqa: E402
from aetherius.recorder.gesture_recorder import segment_gestures  # noqa: E402

_LOGIN_HTML = """<!doctype html><html><body>
  <form>
    <input id="username" name="username" autocomplete="username">
    <input id="password" name="password" type="password">
    <button data-testid="login" type="button">Log in</button>
  </form>
</body></html>"""


def _login_url() -> str:
    return "data:text/html," + urllib.parse.quote(_LOGIN_HTML)


def _event_from_payload(payload: str) -> RecordedEvent:
    data = json.loads(payload)
    raw = data.get("descriptor")
    return RecordedEvent(
        kind=data["kind"],
        descriptor=_descriptor_from_raw(raw) if raw else None,
        value=data.get("value"),
        key=data.get("key"),
        redacted=bool(data.get("redacted", False)),
    )


def test_blueprint_recorder_captures_a_login_against_real_dom() -> None:
    events: list[RecordedEvent] = []

    def on_capture(_source: dict, payload: str) -> None:
        events.append(_event_from_payload(payload))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_capture", on_capture)
        context.add_init_script(RECORDER_JS)
        page = context.new_page()
        page.goto(_login_url())
        page.fill("#username", "alice")
        page.fill("#password", "s3cr3t")
        page.click("[data-testid='login']")
        page.wait_for_timeout(200)  # let the binding callbacks flush
        browser.close()

    steps, secrets = events_to_steps(events)
    blueprint = assemble_blueprint("test.login", steps, secrets)
    validate_for_act(Blueprint.model_validate(blueprint))  # produced Blueprint must be valid

    # The password is a secret and its typed value is nowhere in the output.
    assert "password" in secrets
    assert "s3cr3t" not in json.dumps(steps)
    # The username (autocomplete=username) was turned into a secret too.
    assert "username" in secrets
    # The button carried a data-testid: it is preferred over a positional css path.
    click = next(s for s in steps if s["action"] == "click")
    assert click["selector"] == '[data-testid="login"]'


def test_gesture_recorder_segments_real_pointer_moves() -> None:
    samples: list[tuple[float, float, float]] = []
    clicks: list[float] = []

    def on_binding(_source: dict, payload: str) -> None:
        data = json.loads(payload)
        for move in data.get("moves", []):
            samples.append((float(move[0]), float(move[1]), float(move[2])))
        if data.get("click") is not None:
            clicks.append(float(data["click"]))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_gesture", on_binding)
        context.add_init_script(GESTURE_RECORDER_JS)
        page = context.new_page()
        page.goto("data:text/html,<body style='height:1500px;width:1500px'></body>")
        for i in range(40):
            page.mouse.move(100 + i * 5, 120)
        page.mouse.click(300, 120)
        page.wait_for_timeout(400)  # setInterval flush (250ms) + click flush
        browser.close()

    gestures = segment_gestures(samples, clicks)
    assert len(gestures) >= 1
    assert gestures[0][0] == (0.0, 0.0, 0.0)  # rebased to the origin
