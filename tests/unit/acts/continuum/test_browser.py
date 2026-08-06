"""Tests for acts/continuum/browser.py — the parts that need no real browser.

Constructing a BrowserSession does not import Playwright (that happens lazily in start()), so the
slow-motion decision — the fix that keeps debug slow_mo from shredding humanized gestures — is
unit-testable here.
"""

from __future__ import annotations

import pytest

from aetherius.acts.continuum import browser as browser_mod
from aetherius.acts.continuum.browser import _DEBUG_SLOW_MO_MS, BrowserSession
from aetherius.stealth.humanizer.input import HumanInput
from aetherius.stealth.policy import OFF, StealthPolicy

pytestmark = pytest.mark.unit


def _slow_mo(debug: bool, policy: StealthPolicy) -> int:
    return BrowserSession(debug=debug, stealth=policy)._slow_mo_ms()


class _FakePage:
    """Minimal stand-in for a Playwright page: records the close handler it is given."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.close_handler = None

    def on(self, event: str, handler) -> None:  # type: ignore[no-untyped-def]
        if event == "close":
            self.close_handler = handler


class _FakeContext:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


def test_no_slow_mo_outside_debug() -> None:
    assert _slow_mo(False, OFF) == 0
    assert _slow_mo(False, StealthPolicy(mouse="gestures")) == 0


def test_debug_without_stealth_keeps_slow_mo() -> None:
    assert _slow_mo(True, OFF) == _DEBUG_SLOW_MO_MS


def test_debug_with_fingerprint_only_keeps_slow_mo() -> None:
    # Fingerprint touches no inputs, so plain actions still benefit from slow-motion.
    assert _slow_mo(True, StealthPolicy(fingerprint="chrome-desktop")) == _DEBUG_SLOW_MO_MS


@pytest.mark.parametrize(
    "policy",
    [
        StealthPolicy(mouse="gestures"),
        StealthPolicy(keyboard="human"),
        StealthPolicy(scroll="eased"),
    ],
)
def test_humanized_inputs_disable_slow_mo_even_in_debug(policy: StealthPolicy) -> None:
    assert _slow_mo(True, policy) == 0


# ── raw-action pacing in debug (counterpart to slow_mo) ────────────────────────
def _pace_slept(debug: bool, policy: StealthPolicy, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(browser_mod.time, "sleep", slept.append)
    BrowserSession(debug=debug, stealth=policy).pace_raw_action()
    return slept


def test_pace_raw_action_paces_only_when_slow_mo_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # Humanized + debug is exactly when slow_mo is 0, so raw ops need the manual delay.
    assert _pace_slept(True, StealthPolicy(mouse="gestures"), monkeypatch) == [
        _DEBUG_SLOW_MO_MS / 1000
    ]


def test_pace_raw_action_is_noop_when_slow_mo_covers_or_debug_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _pace_slept(False, StealthPolicy(mouse="gestures"), monkeypatch) == []
    assert _pace_slept(True, OFF, monkeypatch) == []  # slow_mo already paces raw ops here


# ── user-agent override (the one knob the embedded engine shares) ─────────────
def _context_options(policy: StealthPolicy) -> dict[str, object]:
    return BrowserSession(stealth=policy)._context_options()


def test_no_context_options_without_stealth() -> None:
    assert _context_options(OFF) == {}


def test_user_agent_alone_is_the_only_context_option() -> None:
    # A Blueprint that only needs the desktop DOM of a portal must not silently get a whole
    # fingerprint profile with it — the embedded engine would not give it one.
    assert _context_options(StealthPolicy(user_agent="Mozilla/5.0 (Macintosh)")) == {
        "user_agent": "Mozilla/5.0 (Macintosh)"
    }


def test_explicit_user_agent_overrides_the_profile() -> None:
    options = _context_options(
        StealthPolicy(fingerprint="chrome-desktop", user_agent="Mozilla/5.0 (Macintosh)")
    )
    assert options["user_agent"] == "Mozilla/5.0 (Macintosh)"
    assert "viewport" in options  # the rest of the profile is untouched


# ── multi-tab following ────────────────────────────────────────────────────────
def test_on_new_page_becomes_active_and_repoints_humanizer() -> None:
    session = BrowserSession(stealth=StealthPolicy(mouse="gestures"))
    old, new = _FakePage("old"), _FakePage("new")
    session._page = old
    session._human = HumanInput(old, session._stealth)

    session._on_new_page(new)

    assert session.page is new
    assert session._human is not None and session._human.page is new
    assert new.close_handler == session._on_page_close  # close of the new tab is now watched


def test_on_page_close_falls_back_to_a_surviving_page() -> None:
    session = BrowserSession()
    old, new = _FakePage("old"), _FakePage("new")
    session._context = _FakeContext([old, new])
    session._page = new

    session._on_page_close(new)

    assert session.page is old  # stranded on the closed tab -> back to the survivor


def test_on_page_close_ignores_inactive_tab() -> None:
    session = BrowserSession()
    old, new = _FakePage("old"), _FakePage("new")
    session._context = _FakeContext([old, new])
    session._page = new

    session._on_page_close(old)  # a background tab closing must not move the active page

    assert session.page is new
