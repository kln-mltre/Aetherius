"""Integration checks for the Jalon 2-A substrate against a real headless Chromium.

Two seams the cognitive Acts (Oracle/Phantom) rely on: ``_perception.capture`` snapshots the live
page in CSS pixels (so grounder boxes and mouse coordinates share one frame of reference), and
``HumanInput.click_at``/``type_at`` land a coordinate-based interaction through the humanizer on
Continuum's ``BrowserSession``. Self-contained ``data:`` page; marked ``browser``: skipped in
base CI.
"""

from __future__ import annotations

import struct
import urllib.parse

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.integration]
pytest.importorskip("playwright")

from collections.abc import Iterator  # noqa: E402

from aetherius.acts._perception import capture  # noqa: E402
from aetherius.acts.continuum.browser import BrowserSession  # noqa: E402
from aetherius.stealth.policy import StealthPolicy  # noqa: E402

# Fixed-position controls, so their viewport coordinates are known without any DOM query — the
# same situation a grounder puts us in: "click (160, 100)", no locator anywhere.
_PAGE_HTML = """<!doctype html>
<html><body>
  <button style="position:fixed;left:100px;top:80px;width:120px;height:40px"
          onclick="document.getElementById('out').textContent = 'clicked'">Go</button>
  <input id="field" style="position:fixed;left:100px;top:160px;width:200px;height:30px">
  <div id="out"></div>
</body></html>"""
_PAGE_URL = "data:text/html," + urllib.parse.quote(_PAGE_HTML)


def _png_dimensions(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])


@pytest.fixture(scope="module")
def session() -> Iterator[BrowserSession]:
    browser = BrowserSession(
        timeout_ms=8000, stealth=StealthPolicy(mouse="gestures", keyboard="human")
    )
    browser.start()
    yield browser
    browser.close()


def test_capture_snapshots_the_viewport_in_css_pixels(session: BrowserSession) -> None:
    page = session.page
    page.goto(_PAGE_URL)

    perception = capture(page)

    width, height = page.viewport_size["width"], page.viewport_size["height"]
    assert perception.viewport == (width, height)
    # scale="css": the image is exactly viewport-sized, whatever the device pixel ratio.
    assert _png_dimensions(perception.screenshot) == (width, height)
    assert perception.url is not None and perception.url.startswith("data:")
    assert perception.dom is None


def test_capture_includes_the_dom_on_demand(session: BrowserSession) -> None:
    page = session.page
    page.goto(_PAGE_URL)
    perception = capture(page, include_dom=True)
    assert perception.dom is not None and 'id="field"' in perception.dom


def test_click_at_lands_through_the_humanizer(session: BrowserSession) -> None:
    page = session.page
    page.goto(_PAGE_URL)
    human = session.human
    assert human is not None  # the policy humanizes inputs, so the facade is wired

    human.click_at(160.0, 100.0)  # center of the fixed button

    assert page.text_content("#out") == "clicked"


def test_type_at_focuses_and_types(session: BrowserSession) -> None:
    page = session.page
    page.goto(_PAGE_URL)
    human = session.human
    assert human is not None

    human.type_at(150.0, 175.0, "aether")

    assert page.input_value("#field") == "aether"
