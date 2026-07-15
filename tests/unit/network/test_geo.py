"""Tests for network/geo.py — country-to-fingerprint-hint coherence."""

from __future__ import annotations

import pytest

from aetherius.core.errors import BlueprintValidationError
from aetherius.network.geo import geo_hint

pytestmark = pytest.mark.unit


def test_known_country_returns_coherent_hints() -> None:
    hint = geo_hint("FR")
    assert hint.country == "FR"
    assert hint.timezone_id == "Europe/Paris"
    assert hint.locale == "fr-FR"
    assert hint.languages[0] == "fr-FR"


def test_country_code_is_case_insensitive() -> None:
    assert geo_hint("fr") == geo_hint("FR")


def test_unknown_country_fails_loud() -> None:
    with pytest.raises(BlueprintValidationError, match="ZZ"):
        geo_hint("ZZ")


def test_every_hint_is_internally_coherent() -> None:
    # A locale like "fr-FR" should be the first advertised language for each curated country.
    from aetherius.network.geo import _HINTS

    for country, hint in _HINTS.items():
        assert hint.country == country
        assert hint.languages, f"{country} advertises no languages"
        assert hint.locale == hint.languages[0], f"{country}: locale and primary language disagree"
        assert "/" in hint.timezone_id, f"{country}: timezone is not an IANA id"
