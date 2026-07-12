"""Transport selection for the Vector engine: proxy routing and optional browser-TLS impersonation.

Basic HTTP/HTTPS proxying needs nothing extra (httpx supports it natively). SOCKS5 needs the
``[network]`` extra (``socksio``). Defeating JA3/JA4 TLS fingerprinting needs a browser-impersonating
backend (``curl_cffi``, also in ``[network]``); without it, requesting impersonation raises a clear
:class:`~aetherius.core.errors.DependencyError`. Continuum (a real browser) needs none of this — its
TLS handshake is genuine Chromium.
"""

from __future__ import annotations

from typing import Any

from .identity import NetworkIdentity

_PENDING = "Jalon 1.5-G (network): transport selection not implemented yet."


def httpx_proxy_kwargs(identity: NetworkIdentity) -> dict[str, Any]:
    """Keyword arguments for ``httpx.Client(...)`` implementing *identity*'s proxy (``{}`` if none)."""
    raise NotImplementedError(_PENDING)


def impersonation_available() -> bool:
    """Whether the optional TLS-impersonation backend (``curl_cffi``) is importable."""
    raise NotImplementedError(_PENDING)
