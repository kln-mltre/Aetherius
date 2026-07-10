"""End-to-end recorder capture against a real Chromium.

The recorder itself opens a *headed* browser for a human to drive, which cannot run in a headless CI
job. So these tests inject the very same scripts into a headless browser and drive the demonstration
with Playwright — exercising the real capture/overlay JS, descriptor parsing, selector uniqueness and
group detection (measured against a live DOM), the transform, and the extended ``extract`` engine.
The headed launch/pump glue is thin and covered by the manual "Tester" flow in docs/recorder.md.

Marked ``browser``: skipped in the base CI (no [browser] extra), run by the dedicated browser job.
"""

from __future__ import annotations

import json
import urllib.parse
from unittest.mock import patch

import httpx
import pytest

pytestmark = pytest.mark.browser
pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

from aetherius.core.blueprint.models import Blueprint  # noqa: E402
from aetherius.core.blueprint.validator import validate_for_act  # noqa: E402
from aetherius.core.runtime.engine import RunEngine  # noqa: E402
from aetherius.core.runtime.result import RunStatus  # noqa: E402
from aetherius.recorder._capture_js import RECORDER_JS  # noqa: E402
from aetherius.recorder._gesture_js import GESTURE_RECORDER_JS  # noqa: E402
from aetherius.recorder._overlay_js import OVERLAY_JS  # noqa: E402
from aetherius.recorder._selector_js import SELECTOR_JS  # noqa: E402
from aetherius.recorder._transform import events_to_steps  # noqa: E402
from aetherius.recorder._vector_js import VECTOR_JS  # noqa: E402
from aetherius.recorder.blueprint_recorder import assemble_blueprint  # noqa: E402
from aetherius.recorder.capture import RecordedEvent, _descriptor_from_raw  # noqa: E402
from aetherius.recorder.gesture_recorder import segment_gestures  # noqa: E402
from aetherius.recorder.vector_backend import transform as vector_transform  # noqa: E402

_LOGIN_HTML = """<!doctype html><html><body>
  <form>
    <input id="username" name="username" autocomplete="username">
    <input id="password" name="password" type="password">
    <button data-testid="login" type="button">Log in</button>
  </form>
</body></html>"""

_LIST_HTML = """<!doctype html><html><body>
  <div class="quote"><span class="text">T1</span><span class="author">A1</span></div>
  <div class="quote"><span class="text">T2</span><span class="author">A2</span></div>
  <div class="quote"><span class="text">T3</span><span class="author">A3</span></div>
</body></html>"""


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html)


def _event_from_payload(payload: str) -> RecordedEvent:
    """Mirror of capture._on_binding, for driving the transform from a raw binding payload."""
    data = json.loads(payload)
    raw = data.get("descriptor")
    return RecordedEvent(
        kind=data["kind"],
        descriptor=_descriptor_from_raw(raw) if raw else None,
        value=data.get("value"),
        key=data.get("key"),
        url=data.get("href"),  # a link click carries its resolved URL
        redacted=bool(data.get("redacted", False)),
        config={k: v for k, v in data.items() if k not in ("kind", "descriptor")},
    )


def test_blueprint_recorder_captures_a_login_against_real_dom() -> None:
    events: list[RecordedEvent] = []

    def on_capture(_source: dict, payload: str) -> None:
        events.append(_event_from_payload(payload))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_capture", on_capture)
        context.add_init_script(SELECTOR_JS)
        context.add_init_script(RECORDER_JS)
        page = context.new_page()
        page.goto(_data_url(_LOGIN_HTML))
        page.fill("#username", "alice")
        page.fill("#password", "s3cr3t")
        page.click("[data-testid='login']")
        page.wait_for_timeout(200)  # let the binding callbacks flush
        browser.close()

    steps, secrets, _, _ = events_to_steps(events)
    validate_for_act(Blueprint.model_validate(assemble_blueprint("test.login", steps, secrets)))

    assert "password" in secrets and "username" in secrets
    assert "s3cr3t" not in json.dumps(steps)  # the password value is never in the output
    click = next(s for s in steps if s["action"] == "click")
    assert click["selector"] == '[data-testid="login"]'  # data-testid beats a positional path


_AMBIGUOUS_TEXT_HTML = """<!doctype html><html><body>
  <h3>License</h3>
  <a class="lic" href="/kln/Aetherius/blob/main/LICENSE" onclick="event.preventDefault()">License</a>
  <a href="#foot" onclick="event.preventDefault()">View license</a>
</body></html>"""


def test_link_click_prefers_href_over_ambiguous_text() -> None:
    """Reproduces the GitHub 'License' bug: text matches many, so the link must use its href."""
    events: list[RecordedEvent] = []

    def on_capture(_source: dict, payload: str) -> None:
        events.append(_event_from_payload(payload))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_capture", on_capture)
        context.add_init_script(SELECTOR_JS)
        context.add_init_script(RECORDER_JS)
        page = context.new_page()
        page.goto(_data_url(_AMBIGUOUS_TEXT_HTML))
        page.click("a.lic")
        page.wait_for_timeout(150)
        browser.close()

    steps, _, _, _ = events_to_steps(events)
    click = next(s for s in steps if s["action"] == "click")
    assert click["selector"] == 'a[href="/kln/Aetherius/blob/main/LICENSE"]'
    assert "selector_type" not in click  # css, not a fragile get_by_text


_LINK_HTML = """<!doctype html><html><body>
  <a class="go" href="https://example.com/page" onclick="event.preventDefault()">Open the page</a>
</body></html>"""


def test_link_click_is_recorded_as_a_navigate_not_a_click() -> None:
    """Browsing by clicking links must produce robust navigate steps, not fragile selector clicks."""
    events: list[RecordedEvent] = []

    def on_capture(_source: dict, payload: str) -> None:
        events.append(_event_from_payload(payload))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_capture", on_capture)
        context.add_init_script(SELECTOR_JS)
        context.add_init_script(RECORDER_JS)
        page = context.new_page()
        page.goto(_data_url(_LINK_HTML))
        page.click("a.go")
        page.wait_for_timeout(150)
        browser.close()

    steps, _, _, _ = events_to_steps(events)
    assert {"action": "navigate", "url": "https://example.com/page"} in steps
    assert not any(s["action"] == "click" for s in steps)  # the link is a navigate, not a click


def test_overlay_records_pick_produces_a_runnable_scrape() -> None:
    events: list[RecordedEvent] = []

    def on_capture(_source: dict, payload: str) -> None:
        events.append(_event_from_payload(payload))

    url = _data_url(_LIST_HTML)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_capture", on_capture)
        context.add_init_script(SELECTOR_JS)
        context.add_init_script(OVERLAY_JS)
        page = context.new_page()
        page.goto(url)
        # Drive the overlay's emit API directly (the panel UI just calls this).
        page.evaluate(
            """() => {
              const c = document.querySelector('.quote');
              window.__aeOverlay.emitRecords(c, [
                { name: 'text', el: c.querySelector('.text'), as: 'text' },
                { name: 'author', el: c.querySelector('.author'), as: 'text' },
              ], 'quotes');
            }"""
        )
        page.wait_for_timeout(100)
        browser.close()

    assert len(events) == 1 and events[0].kind == "extract_records"
    steps, secrets, inputs, outputs = events_to_steps(events)
    steps.insert(0, {"action": "navigate", "url": url})  # make it runnable standalone
    blueprint = assemble_blueprint("test.scrape", steps, secrets, inputs=inputs, outputs=outputs)

    loaded = Blueprint.model_validate(blueprint)
    validate_for_act(loaded)
    result = RunEngine().run(loaded)
    assert result.status is RunStatus.SUCCESS, result.error
    assert result.outputs["quotes"] == [
        {"text": "T1", "author": "A1"},
        {"text": "T2", "author": "A2"},
        {"text": "T3", "author": "A3"},
    ]


_API_JSON = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}]


def test_vector_recorder_captures_an_api_call_and_the_blueprint_runs() -> None:
    """Vector recorder: capture a fetch (mocked in-browser), pick fields, run the produced Blueprint."""
    events: list[dict] = []

    def on_capture(_source: dict, payload: str) -> None:
        events.append(json.loads(payload))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.expose_binding("__aetherius_capture", on_capture)
        context.add_init_script(VECTOR_JS)
        context.route(
            "https://api.test/**",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(_API_JSON)
            ),
        )
        page = context.new_page()
        page.goto("data:text/html,<body>api demo</body>")
        page.evaluate("async () => { await fetch('https://api.test/users'); }")
        page.wait_for_timeout(200)  # let the patched fetch record the response
        page.evaluate(
            """() => {
              const r = window.__aeVector.requests.find((x) => x.url.includes('/users'));
              window.__aeVector.emit(r, { name: 'users', path: '$[*]', fields: { name: '$.name' } });
            }"""
        )
        page.wait_for_timeout(100)
        browser.close()

    picks = [e for e in events if e.get("kind") == "http_request"]
    assert len(picks) == 1
    result = vector_transform(picks)
    blueprint = assemble_blueprint(
        "test.api",
        result.steps,
        result.secrets,
        act="vector",
        inputs=result.inputs,
        outputs=result.outputs,
    )
    loaded = Blueprint.model_validate(blueprint)
    validate_for_act(loaded)

    transport = httpx.MockTransport(
        lambda _req: httpx.Response(
            200, json=_API_JSON, headers={"content-type": "application/json"}
        )
    )
    with patch("httpx.Client", return_value=httpx.Client(transport=transport)):
        run_result = RunEngine().run(loaded)
    assert run_result.status is RunStatus.SUCCESS, run_result.error
    assert run_result.outputs["users"] == [{"name": "Ada"}, {"name": "Bob"}]


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
