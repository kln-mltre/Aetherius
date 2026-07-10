"""Tests for console/theme.py — pure data, no App required."""

from __future__ import annotations

import pytest

from aetherius.console.theme import ACT_ACCENT, ACT_LABELS, AETHERIUS_THEME, WORDMARK, act_color
from aetherius.core.blueprint.models import Blueprint

pytestmark = pytest.mark.unit

_ALL_ACTS = Blueprint.model_fields["act"].annotation.__args__  # Literal["vector", ...]


def test_theme_has_a_name() -> None:
    assert AETHERIUS_THEME.name == "aetherius"


def test_theme_is_dark() -> None:
    # Deliberate product decision: light backgrounds read poorly in terminals.
    assert AETHERIUS_THEME.dark is True


def test_wordmark_rows_are_aligned() -> None:
    # A ragged wordmark renders visibly broken; every row must have the same width.
    assert len({len(row) for row in WORDMARK}) == 1


@pytest.mark.parametrize("act", _ALL_ACTS)
def test_every_act_has_a_color_and_label(act: str) -> None:
    assert act in ACT_ACCENT
    assert act in ACT_LABELS


def test_act_color_mutes_pending_acts() -> None:
    # A runnable Act wears its own accent; a pending one is muted, whatever its accent.
    assert act_color("continuum", implemented=True) == ACT_ACCENT["continuum"]
    assert act_color("oracle", implemented=False) != ACT_ACCENT["oracle"]
