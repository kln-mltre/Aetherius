"""End-to-end Act II (Continuum) run with discretion on, against a real headless Chromium.

Exercises the whole stealth seam through the engine: an active policy must wear its fingerprint
(navigator.webdriver masked, the profile's platform applied) and route the interactive steps through
the humanized layer (gesture clicks + human typing) while still producing the correct extraction.
Self-contained ``data:`` page, so no external host is needed. Marked ``browser``: skipped in base CI.
"""

from __future__ import annotations

import urllib.parse

import pytest

pytestmark = pytest.mark.browser
pytest.importorskip("playwright")

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
                  '<span class=\\'echo\\'>' + document.getElementById('username').value + '</span>';
    document.body.appendChild(d);">Login</button>
</body></html>"""


def _login_page_url() -> str:
    return "data:text/html," + urllib.parse.quote(_LOGIN_HTML)


def _blueprint() -> Blueprint:
    return Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test.stealth.login",
            "act": "continuum",
            "options": {"timeout_ms": 8000, "stealth": "human"},
            "steps": [
                {"id": "go", "action": "navigate", "url": _login_page_url()},
                {"action": "fill", "selector": "#username", "value": "bob"},
                {"action": "fill", "selector": "#password", "value": "secret"},
                {"action": "click", "selector": "#submit"},
                {"action": "wait_for", "selector": ".dashboard", "timeout_ms": 8000},
                {
                    "id": "fp",
                    "action": "evaluate",
                    "expression": (
                        "() => ({ webdriver: navigator.webdriver === undefined,"
                        " plugins: navigator.plugins.length, platform: navigator.platform })"
                    ),
                },
                {
                    "id": "profile",
                    "action": "extract",
                    "outputs": {
                        "firstName": {"selector": ".firstname", "as": "text"},
                        "echo": {"selector": ".echo", "as": "text"},
                    },
                },
            ],
            "outputs": {
                "firstName": "{{ steps.profile.firstName }}",
                "echo": "{{ steps.profile.echo }}",
                "webdriver_masked": "{{ steps.fp.result.webdriver }}",
                "plugins": "{{ steps.fp.result.plugins }}",
                "platform": "{{ steps.fp.result.platform }}",
            },
        }
    )


def test_stealth_run_masks_fingerprint_and_humanizes_inputs() -> None:
    result = RunEngine().run(_blueprint())
    assert result.status is RunStatus.SUCCESS, result.error
    # Humanized fill + gesture click drove the real form: the dashboard rendered with the typed value.
    assert result.outputs["firstName"] == "Bob"
    assert result.outputs["echo"] == "bob"
    # Fingerprint patch + profile init script are live on the page.
    assert result.outputs["webdriver_masked"] is True
    assert result.outputs["plugins"] > 0
    assert result.outputs["platform"] == "Win32"
