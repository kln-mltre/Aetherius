"""Tests for stealth/fingerprint/profile.py — coherent identity presets."""

from __future__ import annotations

import pytest

from aetherius.core.errors import BlueprintValidationError
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
