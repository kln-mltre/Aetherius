"""Tests for acts/oracle/locator.py — confidence floor and off-center point picking."""

from __future__ import annotations

from random import Random

import pytest

from aetherius.acts._cognition.provider import GroundResult
from aetherius.acts._perception import Perception
from aetherius.acts.oracle.locator import locate, point_in_box
from aetherius.core.errors import CognitionError
from aetherius.core.runtime.selector import Box, Target

pytestmark = pytest.mark.unit

_BOX = Box(x=100.0, y=80.0, width=120.0, height=40.0)


class _FakeGrounder:
    def __init__(self, result: GroundResult) -> None:
        self.calls: list[str] = []
        self._result = result

    def locate(self, perception: Perception, description: str) -> GroundResult:
        self.calls.append(description)
        return self._result


def _perception() -> Perception:
    return Perception(screenshot=b"png", viewport=(1280, 720))


def test_locate_returns_the_grounded_box() -> None:
    grounder = _FakeGrounder(GroundResult(box=_BOX, confidence=0.9))

    box = locate(grounder, _perception(), Target(vision="the button"))

    assert box == _BOX
    assert grounder.calls == ["the button"]


def test_locate_rejects_low_confidence() -> None:
    grounder = _FakeGrounder(GroundResult(box=_BOX, confidence=0.2))
    with pytest.raises(CognitionError, match="not confident"):
        locate(grounder, _perception(), Target(vision="a ghost element"))


def test_locate_honours_a_custom_floor() -> None:
    grounder = _FakeGrounder(GroundResult(box=_BOX, confidence=0.3))
    box = locate(grounder, _perception(), Target(vision="x"), min_confidence=0.25)
    assert box == _BOX


def test_locate_requires_a_vision_target() -> None:
    grounder = _FakeGrounder(GroundResult(box=_BOX, confidence=1.0))
    with pytest.raises(CognitionError, match="vision"):
        locate(grounder, _perception(), Target(selector="#x"))


def test_point_in_box_stays_in_the_offcenter_band() -> None:
    rng = Random(42)
    for _ in range(200):
        x, y = point_in_box(_BOX, rng)
        assert _BOX.x + 0.3 * _BOX.width <= x <= _BOX.x + 0.7 * _BOX.width
        assert _BOX.y + 0.3 * _BOX.height <= y <= _BOX.y + 0.7 * _BOX.height


def test_point_in_box_is_deterministic_for_a_seeded_rng() -> None:
    assert point_in_box(_BOX, Random(7)) == point_in_box(_BOX, Random(7))
