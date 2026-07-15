"""Tests for stealth/fingerprint/hardening.py — the combined hardening init script (Jalon H)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from aetherius.stealth.fingerprint.hardening import hardening_init_script
from aetherius.stealth.fingerprint.profile import get_profile

pytestmark = pytest.mark.unit


def _script() -> str:
    return hardening_init_script(get_profile("chrome-desktop"))


def test_script_is_a_self_invoking_expression() -> None:
    # An IIFE keeps the patch from leaking symbols into the page's global scope.
    assert _script().strip().startswith("(()")


def test_script_sets_an_observable_marker() -> None:
    # A window marker lets a browser test confirm the hardening installed without a round trip.
    assert "__aetherius_hardening" in _script()


@pytest.mark.parametrize(
    "signal",
    [
        "toDataURL",  # canvas
        "getImageData",
        "getChannelData",  # audio
        "getFloatFrequencyData",
        "measureText",  # fonts
        "devicePixelRatio",  # screen
        "userAgentData",  # client hints
        "getHighEntropyValues",
        "WebGL2RenderingContext",  # webgl2
    ],
)
def test_script_covers_each_hardened_signal(signal: str) -> None:
    assert signal in _script()


def test_values_are_derived_from_the_profile() -> None:
    script = _script()
    profile = get_profile("chrome-desktop")
    # Screen dimensions, the client-hint platform and the WebGL renderer all come from the profile.
    assert str(profile.screen[0]) in script
    assert profile.ua_platform in script
    assert profile.webgl_renderer in script
    assert profile.chrome_major in script  # Sec-CH-UA / userAgentData version


def test_webgl2_reuses_the_unmasked_parameters() -> None:
    script = _script()
    assert "37445" in script and "37446" in script  # UNMASKED_VENDOR/RENDERER_WEBGL


def test_noise_is_deterministic_per_profile() -> None:
    # A fingerprint that changes on every read is itself a tell: same profile -> identical script.
    assert _script() == _script()


def test_different_profiles_seed_different_noise() -> None:
    base = get_profile("chrome-desktop")
    other = replace(base, name="other", user_agent=base.user_agent + " variant")
    assert hardening_init_script(base) != hardening_init_script(other)
