"""Browser-level checks for the network identity (Jalon G): the WebRTC leak guard installs, and a
proxy is bound to the Playwright context. Marked ``browser``: skipped in base CI, and self-contained
(a ``data:`` page, no external host or real proxy needed)."""

from __future__ import annotations

import urllib.parse

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.integration]
pytest.importorskip("playwright")

from aetherius.acts.continuum.browser import BrowserSession  # noqa: E402
from aetherius.network.identity import NetworkIdentity  # noqa: E402
from aetherius.network.proxy import ProxySpec  # noqa: E402

# A data: page never touches the network, so the (unreachable) proxy is irrelevant to navigation; it
# only has to mark the context as proxied so the WebRTC guard is wired on.
_PAGE_URL = "data:text/html," + urllib.parse.quote("<!doctype html><html><body>x</body></html>")
_PROXIED_IDENTITY = NetworkIdentity(proxy=ProxySpec("http", "127.0.0.1", 9))


def test_webrtc_guard_installs_on_a_proxied_context() -> None:
    session = BrowserSession(timeout_ms=8000, identity=_PROXIED_IDENTITY)
    session.start()
    try:
        page = session.page
        page.goto(_PAGE_URL)
        assert page.evaluate("() => window.__aetherius_webrtc_guard === true")
        # The constructor is wrapped, not removed: WebRTC still works, it just cannot leak.
        assert page.evaluate("() => typeof window.RTCPeerConnection === 'function'")
    finally:
        session.close()


def test_no_proxy_leaves_webrtc_untouched() -> None:
    session = BrowserSession(timeout_ms=8000)
    session.start()
    try:
        page = session.page
        page.goto(_PAGE_URL)
        assert page.evaluate("() => window.__aetherius_webrtc_guard === undefined")
    finally:
        session.close()
