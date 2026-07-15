"""Tests for stealth/fingerprint/webrtc.py — the WebRTC leak guard (launch flag + init script)."""

from __future__ import annotations

import pytest

from aetherius.stealth.fingerprint.webrtc import WEBRTC_LAUNCH_FLAGS, webrtc_leak_patch

pytestmark = pytest.mark.unit


def test_launch_flag_forces_proxied_only_udp() -> None:
    assert any("disable_non_proxied_udp" in flag for flag in WEBRTC_LAUNCH_FLAGS)


def test_patch_is_a_self_invoking_expression() -> None:
    # An IIFE keeps the patch from leaking symbols into the page's global scope.
    assert webrtc_leak_patch().strip().startswith("(()")


@pytest.mark.parametrize(
    "signal",
    ["RTCPeerConnection", "onicecandidate", "typ host", "typ srflx", ".local"],
)
def test_patch_addresses_each_leaky_candidate_type(signal: str) -> None:
    assert signal in webrtc_leak_patch()


def test_patch_sets_an_observable_marker() -> None:
    # A window marker lets a browser test confirm the guard installed without a network round trip.
    assert "__aetherius_webrtc_guard" in webrtc_leak_patch()
