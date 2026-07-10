"""Tests for stealth/fingerprint/patch.py — the automation-masking init script."""

from __future__ import annotations

import pytest

from aetherius.stealth.fingerprint.patch import FINGERPRINT_PATCH_JS

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "signal",
    ["navigator", "webdriver", "window.chrome", "permissions", "plugins"],
)
def test_patch_addresses_each_known_signal(signal: str) -> None:
    assert signal in FINGERPRINT_PATCH_JS


def test_patch_is_a_self_invoking_expression() -> None:
    # An IIFE keeps the patch from leaking symbols into the page's global scope.
    assert FINGERPRINT_PATCH_JS.strip().startswith("(()")
