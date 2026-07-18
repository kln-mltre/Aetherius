"""Tests for acts/oracle/scan.py — the scroll-scan grounding loop.

Driven with a scripted fake page (scroll metrics + wheel bookkeeping, real-enough screenshot for
the shared capture()) and a scripted grounder, so the loop's economy is asserted exactly: one
grounding call per look, scroll only after a failed look, wrap-to-top only for mid-page starts,
and the hard attempt cap.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts._cognition.provider import GroundResult
from aetherius.acts._perception import Perception
from aetherius.acts.oracle.scan import _MAX_ATTEMPTS, ground_scanning
from aetherius.core.errors import CognitionError
from aetherius.core.runtime.selector import Box

pytestmark = pytest.mark.unit

_BOX = Box(x=100.0, y=80.0, width=120.0, height=40.0)
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class _Mouse:
    def __init__(self, page: "_FakePage") -> None:
        self._page = page

    def wheel(self, dx: float, dy: float) -> None:
        self._page.wheels.append(dy)
        self._page.y = min(self._page.y + dy, self._page.h - self._page.vh)


class _FakePage:
    """A scrollable page: enough surface for capture() and the scan's metrics probe."""

    def __init__(self, height: float = 2000.0, vh: float = 720.0, y: float = 0.0) -> None:
        self.y = y
        self.vh = vh
        self.h = height
        self.wheels: list[float] = []
        self.jumps_to_top = 0
        self.mouse = _Mouse(self)
        self.url = "https://x"

    def evaluate(self, script: str) -> Any:
        if "scrollTo" in script:
            self.y = 0.0
            self.jumps_to_top += 1
            return None
        return {"y": self.y, "vh": self.vh, "h": self.h}

    def screenshot(self, **kwargs: Any) -> bytes:
        return _PNG

    @property
    def viewport_size(self) -> dict[str, int]:
        return {"width": 1280, "height": int(self.vh)}

    def content(self) -> str:
        return "<html></html>"


class _ScriptedGrounder:
    """Replays a confidence per look; reports the box on the first confident one."""

    def __init__(self, confidences: list[float]) -> None:
        self.calls = 0
        self._confidences = confidences

    def locate(self, perception: Perception, description: str) -> GroundResult:
        confidence = self._confidences[min(self.calls, len(self._confidences) - 1)]
        self.calls += 1
        return GroundResult(box=_BOX, confidence=confidence)


def _no_sleep(seconds: float) -> None:
    pass


def test_visible_target_costs_a_single_look_and_no_scroll() -> None:
    page = _FakePage()
    grounder = _ScriptedGrounder([0.9])

    box = ground_scanning(page, None, grounder, "x", min_confidence=0.5, sleep=_no_sleep)

    assert box == _BOX
    assert grounder.calls == 1
    assert page.wheels == []


def test_below_fold_target_is_found_after_scrolling() -> None:
    page = _FakePage(height=3000.0)
    grounder = _ScriptedGrounder([0.1, 0.2, 0.95])

    box = ground_scanning(page, None, grounder, "x", min_confidence=0.5, sleep=_no_sleep)

    assert box == _BOX
    assert grounder.calls == 3
    assert page.wheels == [576.0, 576.0]  # 0.8 * viewport height per step


def test_humanized_scroll_is_used_when_discretion_is_on() -> None:
    page = _FakePage(height=3000.0)
    human = MagicMock()
    # The human facade owns the scroll; the fake page's own wheel must stay untouched.
    human.scroll_by.side_effect = lambda dy: _Mouse(page).wheel(0, dy)
    grounder = _ScriptedGrounder([0.1, 0.9])

    ground_scanning(page, human, grounder, "x", min_confidence=0.5, sleep=_no_sleep)

    human.scroll_by.assert_called_once_with(576.0)


def test_absent_target_scans_to_the_bottom_then_fails() -> None:
    # 2000px page, 720px viewport: looks at y = 0, 576, 1152, 1280 (bottom) -> four looks.
    page = _FakePage(height=2000.0)
    grounder = _ScriptedGrounder([0.2])

    with pytest.raises(CognitionError, match="4 looks"):
        ground_scanning(page, None, grounder, "a ghost", min_confidence=0.5, sleep=_no_sleep)

    assert grounder.calls == 4
    assert page.jumps_to_top == 0


def test_mid_page_start_wraps_to_the_top_to_cover_what_was_above() -> None:
    page = _FakePage(height=2000.0, y=800.0)
    grounder = _ScriptedGrounder([0.1, 0.1, 0.95])  # found on the first look after the wrap

    box = ground_scanning(page, None, grounder, "x", min_confidence=0.5, sleep=_no_sleep)

    assert box == _BOX
    assert page.jumps_to_top == 1
    assert grounder.calls == 3


def test_total_looks_are_hard_capped() -> None:
    page = _FakePage(height=100_000.0)
    grounder = _ScriptedGrounder([0.0])

    with pytest.raises(CognitionError):
        ground_scanning(page, None, grounder, "x", min_confidence=0.5, sleep=_no_sleep)

    assert grounder.calls == _MAX_ATTEMPTS
