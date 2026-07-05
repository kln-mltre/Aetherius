"""Human typing: variable per-session speed, occasional typo-and-correct, per-character delays.

Uniform keystroke timing is an obvious tell. :func:`plan_typing` builds the whole keystroke plan up
front — a pure function of the text and an ``rng`` — so it is fully unit-tested without a keyboard:
a per-call base speed (some people type faster than others), a small chance of a typo immediately
corrected with backspace, longer pauses on spaces (word boundaries) and on special characters that
need a modifier. :func:`human_type` just plays that plan against a Playwright keyboard.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from random import Random
from typing import Any, Literal

from .timing import Sleeper, precise_sleep

# Probability a character is preceded by a wrong keystroke that gets corrected.
_TYPO_PROB = 0.05
# Never dip below this: the DOM needs time to register each keystroke.
_MIN_DELAY_S = 0.05
_SPECIAL_KEYS = frozenset({"#", "@"})
_DEFAULT_RNG = Random()


@dataclass(frozen=True, slots=True)
class KeyEvent:
    """One planned keyboard event: type a character or press a key, then wait ``delay`` seconds."""

    kind: Literal["type", "press"]
    value: str
    delay: float


def _char_delay(char: str, base_speed: float, rng: Random) -> float:
    """Delay after typing *char*: base session speed plus per-character adjustments, floored."""
    delay = base_speed + rng.uniform(-0.04, 0.05)
    if char == " ":
        delay += rng.uniform(0.08, 0.15)  # brief pause between words
    if char in _SPECIAL_KEYS:
        delay += rng.uniform(0.4, 0.8)  # modifier reach slows these down
    return max(delay, _MIN_DELAY_S)


def plan_typing(
    text: str, *, rng: Random = _DEFAULT_RNG, typo_prob: float = _TYPO_PROB
) -> list[KeyEvent]:
    """Return the ordered keystroke plan for *text*, including typo corrections and per-key delays."""
    base_speed = rng.uniform(0.08, 0.20)
    events: list[KeyEvent] = []
    for char in text:
        if rng.random() < typo_prob:
            wrong = rng.choice(string.ascii_lowercase)
            events.append(KeyEvent("type", wrong, rng.uniform(0.15, 0.4)))
            events.append(KeyEvent("press", "Backspace", rng.uniform(0.1, 0.2)))
        events.append(KeyEvent("type", char, _char_delay(char, base_speed, rng)))
    return events


def human_type(
    keyboard: Any,
    text: str,
    *,
    rng: Random = _DEFAULT_RNG,
    sleep: Sleeper = precise_sleep,
    typo_prob: float = _TYPO_PROB,
) -> None:
    """Type *text* on a Playwright keyboard following a humanized plan (typos, per-key timing)."""
    for event in plan_typing(text, rng=rng, typo_prob=typo_prob):
        if event.kind == "type":
            keyboard.type(event.value)
        else:
            keyboard.press(event.value)
        sleep(event.delay)
