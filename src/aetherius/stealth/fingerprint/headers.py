"""HTTP header identity for the Vector engine (Phase 1.5, Jalon H).

Vector (HTTP-only) sends httpx's stock headers today — no User-Agent, no client hints — which is a
plain bot signature. This derives a coherent set of default request headers (User-Agent, ``Sec-CH-UA``
family, ``Accept``/``Accept-Language``) from a
:class:`~aetherius.stealth.fingerprint.profile.FingerprintProfile`, so an HTTP-only run wears the same
story as the browser. They are *defaults*: the driver merges them under the Blueprint's explicit
headers, which always win.
"""

from __future__ import annotations

from .profile import FingerprintProfile

# A modern Chromium's top-level navigation Accept. Blueprints that need JSON set their own Accept,
# which overrides this default.
_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
    "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)


def _accept_language(languages: tuple[str, ...]) -> str:
    """Build an ``Accept-Language`` value from the profile's languages, q-values decreasing by 0.1.

    ``("fr-FR", "fr", "en")`` -> ``"fr-FR,fr;q=0.9,en;q=0.8"`` — coherent with the browser's
    ``navigator.languages`` for the same profile.
    """
    parts = [languages[0]] if languages else ["en-US"]
    for index, lang in enumerate(languages[1:], start=1):
        q = max(0.1, 1.0 - index * 0.1)
        parts.append(f"{lang};q={q:.1f}")
    return ",".join(parts)


def http_headers(profile: FingerprintProfile) -> dict[str, str]:
    """Default request headers (UA, client hints, Accept-Language) coherent with *profile*."""
    return {
        "User-Agent": profile.user_agent,
        "Accept": _ACCEPT,
        "Accept-Language": _accept_language(profile.languages),
        "Sec-CH-UA": profile.sec_ch_ua(),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": f'"{profile.ua_platform}"',
        "Upgrade-Insecure-Requests": "1",
    }
