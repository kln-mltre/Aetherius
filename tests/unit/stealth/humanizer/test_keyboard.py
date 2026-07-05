"""Tests for stealth/humanizer/keyboard.py — the humanized typing plan."""

from __future__ import annotations

from random import Random
from unittest.mock import MagicMock

import pytest

from aetherius.stealth.humanizer.keyboard import _MIN_DELAY_S, human_type, plan_typing

pytestmark = pytest.mark.unit


def test_plan_without_typos_is_one_event_per_char() -> None:
    events = plan_typing("hello world", rng=Random(0), typo_prob=0.0)
    assert len(events) == len("hello world")
    assert all(e.kind == "type" for e in events)


def test_every_delay_respects_the_floor() -> None:
    events = plan_typing("a b@c", rng=Random(1), typo_prob=0.0)
    assert all(e.delay >= _MIN_DELAY_S for e in events)


def test_typos_insert_wrong_char_then_backspace() -> None:
    events = plan_typing("ab", rng=Random(2), typo_prob=1.0)
    # Each real char is preceded by a wrong keystroke and a Backspace press.
    assert len(events) == 6
    assert events[1].kind == "press" and events[1].value == "Backspace"


def test_human_type_plays_types_and_presses() -> None:
    keyboard = MagicMock()
    human_type(keyboard, "hi", rng=Random(0), sleep=lambda _: None, typo_prob=0.0)
    typed = [c.args[0] for c in keyboard.type.call_args_list]
    assert typed == ["h", "i"]
    keyboard.press.assert_not_called()
