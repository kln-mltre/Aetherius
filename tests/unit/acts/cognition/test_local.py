"""Tests for acts/_cognition/local.py — the grounding-only local provider."""

from __future__ import annotations

import pytest

from aetherius.acts._cognition.local import LocalGrounder
from aetherius.acts._perception import Perception
from aetherius.core.errors import CognitionError

pytestmark = pytest.mark.unit

_PERCEPTION = Perception(screenshot=b"", viewport=(0, 0))


def test_locate_is_a_pending_optional_path() -> None:
    with pytest.raises(NotImplementedError):
        LocalGrounder().locate(_PERCEPTION, "anything")


def test_read_raises_typed_role_error() -> None:
    with pytest.raises(CognitionError, match="only grounds"):
        LocalGrounder().read(_PERCEPTION, "the price list")


def test_plan_raises_typed_role_error() -> None:
    with pytest.raises(CognitionError, match="only grounds"):
        LocalGrounder().plan("goal", [], _PERCEPTION, memory=None)
