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
                  '<span class=\\'unread\\'>3 unread</span>';
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
