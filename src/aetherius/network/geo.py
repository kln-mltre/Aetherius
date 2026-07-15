"""Geographic coherence between the exit IP and the browser fingerprint.

A US exit IP paired with a ``Europe/Paris`` timezone is a glaring tell. When a proxy carries a country
hint, the fingerprint's timezone / locale / languages should follow it. This maps a country to
coherent hints; the fingerprint profile is then derived to match (see docs/phase-1.5/g-network.md).

The country comes from the proxy configuration, not from an online GeoIP lookup (out of scope): the
table below is curated, not sampled. A country outside it fails loud rather than presenting an
incoherent identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import BlueprintValidationError


@dataclass(frozen=True, slots=True)
class GeoHint:
    """Coherent locale/timezone hints for an exit-IP country."""

    country: str  # ISO 3166-1 alpha-2, e.g. "FR"
    timezone_id: str  # e.g. "Europe/Paris"
    locale: str  # e.g. "fr-FR"
    languages: tuple[str, ...]  # e.g. ("fr-FR", "fr", "en")


# Curated table. For countries spanning several timezones (US, CA, AU), a common one is chosen; the
# goal is coherence with the exit IP's country, not pinpoint accuracy. Add entries as coverage needs.
_HINTS: dict[str, GeoHint] = {
    "FR": GeoHint("FR", "Europe/Paris", "fr-FR", ("fr-FR", "fr", "en")),
    "US": GeoHint("US", "America/New_York", "en-US", ("en-US", "en")),
    "GB": GeoHint("GB", "Europe/London", "en-GB", ("en-GB", "en")),
    "DE": GeoHint("DE", "Europe/Berlin", "de-DE", ("de-DE", "de", "en")),
    "ES": GeoHint("ES", "Europe/Madrid", "es-ES", ("es-ES", "es", "en")),
    "IT": GeoHint("IT", "Europe/Rome", "it-IT", ("it-IT", "it", "en")),
    "NL": GeoHint("NL", "Europe/Amsterdam", "nl-NL", ("nl-NL", "nl", "en")),
    "BE": GeoHint("BE", "Europe/Brussels", "fr-BE", ("fr-BE", "fr", "nl", "en")),
    "CH": GeoHint("CH", "Europe/Zurich", "de-CH", ("de-CH", "de", "fr", "en")),
    "PT": GeoHint("PT", "Europe/Lisbon", "pt-PT", ("pt-PT", "pt", "en")),
    "SE": GeoHint("SE", "Europe/Stockholm", "sv-SE", ("sv-SE", "sv", "en")),
    "PL": GeoHint("PL", "Europe/Warsaw", "pl-PL", ("pl-PL", "pl", "en")),
    "CA": GeoHint("CA", "America/Toronto", "en-CA", ("en-CA", "en", "fr-CA")),
    "BR": GeoHint("BR", "America/Sao_Paulo", "pt-BR", ("pt-BR", "pt", "en")),
    "AU": GeoHint("AU", "Australia/Sydney", "en-AU", ("en-AU", "en")),
    "JP": GeoHint("JP", "Asia/Tokyo", "ja-JP", ("ja-JP", "ja", "en")),
    "IN": GeoHint("IN", "Asia/Kolkata", "en-IN", ("en-IN", "en", "hi")),
}


def geo_hint(country: str) -> GeoHint:
    """Return coherent timezone/locale/language hints for an exit-IP *country* code.

    Raises:
        BlueprintValidationError: for a country outside the curated table.
    """
    hint = _HINTS.get(country.strip().upper())
    if hint is None:
        raise BlueprintValidationError(
            f"No geo hint for country {country!r} (supported: {sorted(_HINTS)})."
        )
    return hint
