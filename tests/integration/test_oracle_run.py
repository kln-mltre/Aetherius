"""Integration: a full Oracle run through the engine against a real headless Chromium.

The cognition provider is faked (no network, no [cognition] extra needed): what this proves is the
whole wiring — engine -> OracleDriver -> shared perception -> coordinate actions on Continuum's
real browser session — using a self-contained ``data:`` page whose fixed-position controls have
known viewport boxes, exactly what a real grounder would report. Marked ``browser``: skipped in
base CI.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.integration]
pytest.importorskip("playwright")

from aetherius.acts._cognition.provider import GroundResult  # noqa: E402
from aetherius.acts._perception import Perception  # noqa: E402
from aetherius.core.blueprint.models import Blueprint  # noqa: E402
from aetherius.core.runtime.engine import RunEngine  # noqa: E402
from aetherius.core.runtime.result import RunStatus  # noqa: E402
from aetherius.core.runtime.selector import Box  # noqa: E402

_PAGE_HTML = """<!doctype html>
<html><body>
  <button style="position:fixed;left:100px;top:80px;width:120px;height:40px"
          onclick="document.getElementById('out').textContent = 'clicked'">Go</button>
  <input id="field" style="position:fixed;left:100px;top:160px;width:200px;height:30px">
  <div id="out"></div>
</body></html>"""
_PAGE_URL = "data:text/html," + urllib.parse.quote(_PAGE_HTML)

# Viewport boxes of the fixed-position controls above — what a real grounder would report.
_BOXES = {
    "the Go button": Box(x=100, y=80, width=120, height=40),
    "the name field": Box(x=100, y=160, width=200, height=30),
}


class _FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.perceptions: list[Perception] = []

    def locate(self, perception: Perception, description: str) -> GroundResult:
        self.perceptions.append(perception)
        return GroundResult(box=_BOXES[description], confidence=0.99)

    def read(
        self, perception: Perception, description: str, *, schema: dict[str, Any] | None = None
    ) -> Any:
        self.perceptions.append(perception)
        return "clicked"


def test_oracle_run_clicks_types_and_reads_through_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeProvider()
    monkeypatch.setattr("aetherius.acts.oracle.driver.resolve_provider", lambda vision: provider)

    blueprint = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t.oracle.integration",
            "act": "oracle",
            "options": {"timeout_ms": 8000},
            "steps": [
                {"id": "open", "action": "navigate", "url": _PAGE_URL},
                {"id": "go", "action": "click", "target": {"vision": "the Go button"}},
                {
                    "id": "hail",
                    "action": "type",
                    "target": {"vision": "the name field"},
                    "text": "aether",
                },
                {
                    "id": "checked",
                    "action": "extract",
                    "outputs": {"out": {"selector": "#out", "as": "text"}},
                },
                {
                    "id": "typed",
                    "action": "evaluate",
                    "script": "() => document.getElementById('field').value",
                },
                {"id": "seen", "action": "read", "vision": "the page state"},
            ],
            "outputs": {
                "out": "{{ steps.checked.out }}",
                "typed": "{{ steps.typed.result }}",
                "seen": "{{ steps.seen.data }}",
            },
        }
    )

    result = RunEngine().run(blueprint)

    assert result.status is RunStatus.SUCCESS
    assert result.outputs == {"out": "clicked", "typed": "aether", "seen": "clicked"}
    # The provider perceived real screenshots of the live page (grounding x2, read x1).
    assert len(provider.perceptions) == 3
    assert all(p.screenshot[:8] == b"\x89PNG\r\n\x1a\n" for p in provider.perceptions)
