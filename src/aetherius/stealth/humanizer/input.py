"""HumanInput: the element-level humanized input facade the browser Acts drive.

One object that turns an active :class:`StealthPolicy` into concrete humanized interactions on a
Playwright page. It speaks only Playwright primitives — a ``locator``, ``page.keyboard``,
``page.mouse`` — and never touches selectors or Blueprint params, so the dependency runs one way
(Acts depend on stealth, not the reverse). Each method degrades per feature: with the mouse
humanizer off, a click is a plain ``locator.click`` but typing can still be humanized, and so on.
"""

from __future__ import annotations

from random import Random
from typing import Any

from ..gestures.library import GestureLibrary
from ..policy import StealthPolicy
from .keyboard import human_type
from .mouse import HumanMouse
from .scroll import human_scroll
from .timing import Sleeper, precise_sleep


class HumanInput:
    """Humanized click/hover/fill/type/scroll bound to one page, gated by a :class:`StealthPolicy`."""

    def __init__(
        self,
        page: Any,
        policy: StealthPolicy,
        *,
        rng: Random | None = None,
        sleep: Sleeper = precise_sleep,
        library: GestureLibrary | None = None,
    ) -> None:
        self.page = page
        self.policy = policy
        self._rng = rng or Random()
        self._sleep = sleep
        # Build the gesture mouse only when it is actually requested; otherwise inputs stay plain.
        self._mouse = (
            HumanMouse(page, library, rng=self._rng, sleep=self._sleep)
            if policy.mouse == "gestures"
            else None
        )

    def click(self, locator: Any) -> None:
        if self._mouse is not None:
            self._mouse.click(locator)
        else:
            locator.click()

    def hover(self, locator: Any) -> None:
        if self._mouse is not None:
            self._mouse.move_to_locator(locator)
        else:
            locator.hover()

    def fill(self, locator: Any, value: str) -> None:
        """Focus the field, clear it, then enter *value* (humanized if the keyboard feature is on)."""
        self._focus(locator)
        keyboard = self.page.keyboard
        keyboard.press("Control+a")
        keyboard.press("Delete")
        self._enter_text(value)

    def type(self, locator: Any, text: str) -> None:
        """Focus the field and append *text* without clearing (humanized keyboard when enabled)."""
        self._focus(locator)
        self._enter_text(text)

    def scroll_by(self, amount: float) -> None:
        human_scroll(self.page, amount, rng=self._rng, sleep=self._sleep)

    def park(self) -> None:
        """Idle the cursor away from controls during a wait (no-op unless the mouse is humanized)."""
        if self._mouse is not None:
            self._mouse.park()

    def _focus(self, locator: Any) -> None:
        if self._mouse is not None:
            self._mouse.click(locator)
        else:
            locator.click()

    def _enter_text(self, text: str) -> None:
        if self.policy.keyboard == "human":
            human_type(self.page.keyboard, text, rng=self._rng, sleep=self._sleep)
        else:
            self.page.keyboard.type(text)
