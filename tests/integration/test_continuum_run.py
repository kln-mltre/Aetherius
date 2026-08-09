"""End-to-end Act II (Continuum) run against a real headless Chromium.

Serves a self-contained login page via a ``data:`` URL, so no external host or local server is
needed. Marked ``browser``: skipped in the base CI (where the [browser] extra is absent) and run by
the dedicated browser job (which installs Playwright and its Chromium binary).
"""

from __future__ import annotations

import urllib.parse

import pytest

pytestmark = pytest.mark.browser
pytest.importorskip("playwright")

from aetherius.acts.continuum.debug_overlay import DEBUG_OVERLAY_JS  # noqa: E402
from aetherius.core.blueprint.models import Blueprint  # noqa: E402
from aetherius.core.runtime.engine import RunEngine  # noqa: E402
from aetherius.core.runtime.result import RunStatus  # noqa: E402

_LOGIN_HTML = """<!doctype html>
<html><body>
  <input id="username">
  <input id="password" type="password">
  <button id="submit" onclick="
    var d = document.createElement('div');
    d.className = 'dashboard';
    d.innerHTML = 'Welcome <span class=\\'firstname\\'>Bob</span>' +
                  '<span class=\\'unread\\'>3 unread</span>' +
                  '<ul><li class=\\'item\\'>a</li><li class=\\'item\\'>b</li></ul>';
    document.body.appendChild(d);">Login</button>
</body></html>"""


def _login_page_url() -> str:
    return "data:text/html," + urllib.parse.quote(_LOGIN_HTML)


def _blueprint() -> Blueprint:
    return Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test.continuum.login",
            "act": "continuum",
            "options": {"timeout_ms": 5000},
            "steps": [
                {"id": "go", "action": "navigate", "url": _login_page_url()},
                {"action": "fill", "selector": "#username", "value": "bob"},
                {"action": "fill", "selector": "#password", "value": "secret"},
                {"action": "click", "selector": "#submit"},
                {"action": "wait_for", "selector": ".dashboard", "timeout_ms": 5000},
                # Non-unique selector: exercises the `.first` guard against strict-mode errors.
                {"action": "wait_for", "selector": ".item", "timeout_ms": 5000},
                {
                    "id": "profile",
                    "action": "extract",
                    "outputs": {
                        "firstName": {"selector": ".firstname", "as": "text"},
                        "unread": {"selector": ".unread", "as": "number"},
                    },
                },
            ],
            "outputs": {
                "firstName": "{{ steps.profile.firstName }}",
                "unread": "{{ steps.profile.unread }}",
            },
        }
    )


def test_continuum_login_and_extract() -> None:
    result = RunEngine().run(_blueprint())
    assert result.status is RunStatus.SUCCESS, result.error
    assert result.outputs["firstName"] == "Bob"
    assert result.outputs["unread"] == 3


def test_debug_overlay_injects_cursor_and_ripple() -> None:
    # Drive the overlay script directly (headless), so the debug aid is locked without opening a
    # window or waiting on the debug linger. It must add a cursor and spawn a ripple on click.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.add_init_script(DEBUG_OVERLAY_JS)
        page = context.new_page()
        page.goto(
            "data:text/html,<button id='b' style='position:absolute;top:80px;left:80px'>x</button>"
        )
        assert page.locator(".__ae-cursor").count() == 1
        page.locator("#b").click()
        assert page.locator(".__ae-ripple").count() >= 1
        browser.close()


def test_continuum_wait_for_timeout_fails_with_code() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test.continuum.timeout",
            "act": "continuum",
            "options": {"timeout_ms": 1000},
            "steps": [
                {"id": "go", "action": "navigate", "url": _login_page_url()},
                {
                    "action": "wait_for",
                    "selector": ".never-appears",
                    "timeout_ms": 500,
                    "on_timeout": "fail:LOGIN_FAILED",
                },
            ],
        }
    )
    result = RunEngine().run(bp)
    assert result.status is RunStatus.FAILED
    assert result.error is not None


def test_continuum_unreachable_source_is_a_network_failure() -> None:
    """A refused connection stops the run at ``navigate``, typed as unreachable.

    The whole point is the *class*: left as a raw Playwright error it came back wrapped in a
    ``RunError``, which an application reads as "report this bug" rather than "the service is
    down". Port 4 is privileged and on no browser's blocked list, so the refusal is a real one and
    needs no fixture server. Twin of the embedded engine's host test
    (``sdks/react-native/test/rpc.test.js``) and of the shared conformance case.
    """
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test.continuum.unreachable",
            "act": "continuum",
            "options": {"timeout_ms": 5000},
            "steps": [
                {"id": "go", "action": "navigate", "url": "http://127.0.0.1:4/"},
                {"id": "jamais", "action": "wait_for", "selector": "#absent"},
            ],
        }
    )
    result = RunEngine().run(bp)
    assert result.status is RunStatus.FAILED
    assert result.error is not None and "unreachable" in result.error
    # The run stops *there*: the wait must never start, or the failure would be named after the
    # page instead of after the connection.
    assert [step.step_id for step in result.step_results] == ["go"]
