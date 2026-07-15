"""Tests for stealth/fingerprint/profile.py — coherent identity presets."""

from __future__ import annotations

import pytest

from aetherius.core.errors import BlueprintValidationError
from aetherius.network.geo import geo_hint
from aetherius.stealth.fingerprint.profile import get_profile

pytestmark = pytest.mark.unit


def test_chrome_desktop_context_options_are_coherent() -> None:
    profile = get_profile("chrome-desktop")
    opts = profile.context_options()
    assert opts["user_agent"].startswith("Mozilla/5.0")
    assert set(opts) == {"user_agent", "viewport", "locale", "timezone_id"}
    assert opts["viewport"] == {"width": 1280, "height": 800}


def test_init_script_aligns_hardware_and_webgl() -> None:
    script = get_profile("chrome-desktop").init_script()
    assert "hardwareConcurrency" in script
    assert "37445" in script and "37446" in script  # WebGL vendor/renderer parameters


def test_unknown_profile_raises_typed_error() -> None:
    with pytest.raises(BlueprintValidationError):
        get_profile("nonesuch")


def test_hardening_fields_are_coherent() -> None:
    profile = get_profile("chrome-desktop")
    # The screen is at least as large as the inner viewport, and the client-hint platform differs
    # from navigator.platform ("Windows" vs "Win32") as a real browser reports.
    assert profile.screen[0] >= profile.viewport[0]
    assert profile.ua_platform == "Windows" and profile.platform == "Win32"


def test_sec_ch_ua_is_built_from_the_ua_version() -> None:
    profile = get_profile("chrome-desktop")
    sec_ch_ua = profile.sec_ch_ua()
    assert f'"Chromium";v="{profile.chrome_major}"' in sec_ch_ua
    assert f'"Google Chrome";v="{profile.chrome_major}"' in sec_ch_ua


def test_geo_aligned_replaces_timezone_locale_languages() -> None:
    profile = get_profile("chrome-desktop")
    hint = geo_hint("FR")
    aligned = profile.geo_aligned(hint)
    assert aligned.timezone_id == "Europe/Paris"
    assert aligned.locale == "fr-FR"
    assert aligned.languages == hint.languages
    # The hardware identity (UA, WebGL) is untouched — only the geography follows the exit IP.
    assert aligned.user_agent == profile.user_agent
