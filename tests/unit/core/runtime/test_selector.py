"""Tests for core/runtime/selector.py — Box geometry and the unified Target parsing."""

from __future__ import annotations

import pytest

from aetherius.core.errors import ActionError
from aetherius.core.runtime.selector import Box, Target

pytestmark = pytest.mark.unit


def test_box_center_is_the_middle() -> None:
    assert Box(x=10, y=20, width=100, height=40).center == (60.0, 40.0)


def test_box_center_handles_edges_and_fractions() -> None:
    assert Box(x=0, y=0, width=0, height=0).center == (0.0, 0.0)
    assert Box(x=1.5, y=2.5, width=3.0, height=5.0).center == (3.0, 5.0)


def test_from_step_reads_top_level_selector() -> None:
    target = Target.from_step({"selector": "#login"})
    assert target.selector == "#login"
    assert target.selector_type == "css"
    assert not target.is_vision


def test_from_step_reads_selector_type() -> None:
    target = Target.from_step({"selector": "//button", "selector_type": "xpath"})
    assert target.selector_type == "xpath"


def test_from_step_reads_vision_target() -> None:
    target = Target.from_step({"target": {"vision": "the Post button"}})
    assert target.vision == "the Post button"
    assert target.selector is None
    assert target.is_vision


def test_from_step_reads_nested_selector_target() -> None:
    target = Target.from_step({"target": {"selector": ".price", "selector_type": "text"}})
    assert target.selector == ".price"
    assert target.selector_type == "text"


def test_from_step_rejects_selector_and_vision() -> None:
    with pytest.raises(ActionError, match="not both"):
        Target.from_step({"selector": "#a", "target": {"vision": "the a"}})


def test_from_step_rejects_missing_target() -> None:
    with pytest.raises(ActionError, match="Missing target"):
        Target.from_step({"action": "click"})


def test_from_step_rejects_unknown_selector_type() -> None:
    with pytest.raises(ActionError, match="selector_type"):
        Target.from_step({"selector": "#a", "selector_type": "regex"})
