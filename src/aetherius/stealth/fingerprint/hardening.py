"""Fingerprint hardening (Phase 1.5, Jalon H): the signals the base profile leaves untouched.

The coherent profile (``profile.py``) covers UA / viewport / locale / timezone / platform / cores /
memory / WebGL1. This closes the remaining high-signal gaps that advanced anti-bot systems
cross-check: Canvas and AudioContext fingerprints (subtle, stable per-profile noise), font
enumeration, client hints (``Sec-CH-UA`` / ``navigator.userAgentData``) aligned with the UA, screen
dimensions / ``devicePixelRatio``, and WebGL2. Every override stays coherent with the active
:class:`~aetherius.stealth.fingerprint.profile.FingerprintProfile` — one consistent story, not
scattered spoofs.

Status: jalon en attente. The public shape is fixed here; the implementation lands with Jalon H.
See docs/phase-1.5/h-fingerprint.md.
"""

from __future__ import annotations

from .profile import FingerprintProfile

_PENDING = "Jalon 1.5-H (fingerprint): hardening patches not implemented yet."


def hardening_init_script(profile: FingerprintProfile) -> str:
    """Return the init script closing the Canvas/Audio/fonts/UA-CH/screen/WebGL2 gaps.

    Kept coherent with *profile* so the added signals tell the same story as the base identity.
    """
    raise NotImplementedError(_PENDING)
