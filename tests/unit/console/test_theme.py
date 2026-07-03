"""Tests for console/theme.py — pure data, no App required."""

from __future__ import annotations

import pytest

from aetherius.console.theme import ACT_LABELS, AETHERIUS_THEME, PER_ACT_COLOR
from aetherius.core.blueprint.models import Blueprint

pytestmark = pytest.mark.unit

_ALL_ACTS = Blueprint.model_fields["act"].annotation.__args__  # Literal["vector", ...]


def test_theme_has_a_name() -> None:
    assert AETHERIUS_THEME.name == "aetherius"


@pytest.mark.parametrize("act", _ALL_ACTS)
def test_every_act_has_a_color_and_label(act: str) -> None:
    assert act in PER_ACT_COLOR
    assert act in ACT_LABELS
