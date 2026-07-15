"""Tests for stealth/fingerprint/headers.py — Vector's default HTTP header identity (Jalon H)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from aetherius.stealth.fingerprint.headers import http_headers
from aetherius.stealth.fingerprint.profile import get_profile

pytestmark = pytest.mark.unit


def test_user_agent_matches_the_profile() -> None:
    profile = get_profile("chrome-desktop")
    assert http_headers(profile)["User-Agent"] == profile.user_agent


def test_client_hints_agree_with_the_ua_version() -> None:
    profile = get_profile("chrome-desktop")
    headers = http_headers(profile)
    assert profile.chrome_major in headers["Sec-CH-UA"]
    assert headers["Sec-CH-UA-Mobile"] == "?0"
    assert headers["Sec-CH-UA-Platform"] == f'"{profile.ua_platform}"'


def test_accept_language_is_derived_from_the_profile_languages() -> None:
    profile = replace(get_profile("chrome-desktop"), languages=("fr-FR", "fr", "en"))
    assert http_headers(profile)["Accept-Language"] == "fr-FR,fr;q=0.9,en;q=0.8"


def test_single_language_has_no_q_value() -> None:
    profile = replace(get_profile("chrome-desktop"), languages=("en-US",))
    assert http_headers(profile)["Accept-Language"] == "en-US"
