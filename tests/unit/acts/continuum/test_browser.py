"""Tests for acts/continuum/browser.py — the parts that need no real browser.

Constructing a BrowserSession does not import Playwright (that happens lazily in start()), so the
slow-motion decision — the fix that keeps debug slow_mo from shredding humanized gestures — is
unit-testable here.
"""

from __future__ import annotations

import pytest

from aetherius.acts.continuum.browser import _DEBUG_SLOW_MO_MS, BrowserSession
from aetherius.stealth.policy import OFF, StealthPolicy

pytestmark = pytest.mark.unit


def _slow_mo(debug: bool, policy: StealthPolicy) -> int:
    return BrowserSession(debug=debug, stealth=policy)._slow_mo_ms()


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
