"""Geographic coherence between the exit IP and the browser fingerprint.

A US exit IP paired with a ``Europe/Paris`` timezone is a glaring tell. When a proxy carries a country
hint, the fingerprint's timezone / locale / languages should follow it. This maps a country to
coherent hints; the fingerprint profile is then derived to match (see docs/phase-1.5/g-network.md).
"""

from __future__ import annotations

from dataclasses import dataclass

_PENDING = "Jalon 1.5-G (network): geo coherence not implemented yet."


@dataclass(frozen=True, slots=True)
class GeoHint:
    """Coherent locale/timezone hints for an exit-IP country."""

    country: str  # ISO 3166-1 alpha-2, e.g. "FR"
    timezone_id: str  # e.g. "Europe/Paris"
    locale: str  # e.g. "fr-FR"
    languages: tuple[str, ...]  # e.g. ("fr-FR", "fr", "en")


def geo_hint(country: str) -> GeoHint:
    """Return coherent timezone/locale/language hints for an exit-IP *country* code."""
    raise NotImplementedError(_PENDING)
