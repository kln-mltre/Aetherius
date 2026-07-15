"""Browser-level checks for fingerprint hardening (Jalon H): on a real headless Chromium, the
hardened signals are coherent with the active profile and the Canvas noise is stable between two
reads of the same run. Marked ``browser``: skipped in base CI, and self-contained (a ``data:`` page,
no external host)."""

from __future__ import annotations

import urllib.parse

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.integration]
pytest.importorskip("playwright")

from aetherius.acts.continuum.browser import BrowserSession  # noqa: E402
from aetherius.stealth.fingerprint.profile import get_profile  # noqa: E402
from aetherius.stealth.policy import build_policy  # noqa: E402

_PAGE_URL = "data:text/html," + urllib.parse.quote("<!doctype html><html><body>x</body></html>")

# Draws a canvas twice and returns both data URLs plus the hardened signals, so a single evaluate
# proves both stability (canvasA === canvasB) and coherence with the profile.
_PROBE_JS = """
() => {
  const draw = () => {
    const c = document.createElement('canvas');
    c.width = 200; c.height = 50;
    const ctx = c.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '16px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(0, 0, 100, 25);
    ctx.fillStyle = '#069';
    ctx.fillText('Aetherius fingerprint', 4, 8);
    return c.toDataURL();
  };
  const gl = document.createElement('canvas').getContext('webgl2');
  return {
    canvasA: draw(),
    canvasB: draw(),
    uaPlatform: navigator.userAgentData ? navigator.userAgentData.platform : null,
    screenWidth: screen.width,
    webgl2Renderer: gl ? gl.getParameter(37446) : null,
    hardened: window.__aetherius_hardening === true,
  };
}
"""


def test_hardening_signals_are_coherent_and_stable() -> None:
    profile = get_profile("chrome-desktop")
    session = BrowserSession(timeout_ms=8000, stealth=build_policy("human"))
    session.start()
    try:
        page = session.page
        page.goto(_PAGE_URL)
        probe = page.evaluate(_PROBE_JS)
    finally:
        session.close()

    assert probe["hardened"] is True
    # Deterministic Canvas noise: two reads of the same drawing return identical bytes.
    assert probe["canvasA"] == probe["canvasB"]
    # Client hints and screen follow the profile, not the real host.
    assert probe["uaPlatform"] == profile.ua_platform
    assert probe["screenWidth"] == profile.screen[0]
    # WebGL2's unmasked renderer is aligned like WebGL1 (SwiftShader would otherwise reveal itself).
    assert probe["webgl2Renderer"] == profile.webgl_renderer


def test_no_stealth_leaves_signals_untouched() -> None:
    session = BrowserSession(timeout_ms=8000)
    session.start()
    try:
        page = session.page
        page.goto(_PAGE_URL)
        assert page.evaluate("() => window.__aetherius_hardening === undefined")
    finally:
        session.close()
