"""HTTP header identity for the Vector engine (Phase 1.5, Jalon H).

Vector (HTTP-only) sends httpx's stock headers today — no User-Agent, no client hints — which is a
plain bot signature. This derives a coherent set of default request headers (User-Agent, ``Sec-CH-UA``
family, ``Accept-Language``) from a :class:`~aetherius.stealth.fingerprint.profile.FingerprintProfile`,
so an HTTP-only run wears the same story as the browser.

Status: jalon en attente. The public shape is fixed here; the implementation lands with Jalon H.
"""

from __future__ import annotations

from .profile import FingerprintProfile

_PENDING = "Jalon 1.5-H (fingerprint): Vector header identity not implemented yet."


def http_headers(profile: FingerprintProfile) -> dict[str, str]:
    """Default request headers (UA, client hints, Accept-Language) coherent with *profile*."""
    raise NotImplementedError(_PENDING)
