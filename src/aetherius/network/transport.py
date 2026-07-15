"""Transport selection for the Vector engine: proxy routing and optional browser-TLS impersonation.

Basic HTTP/HTTPS proxying needs nothing extra (httpx supports it natively). SOCKS5 needs the
``[network]`` extra (``socksio``). Defeating JA3/JA4 TLS fingerprinting needs a browser-impersonating
backend (``curl_cffi``, also in ``[network]``); without it, requesting impersonation raises a clear
:class:`~aetherius.core.errors.DependencyError`. Continuum (a real browser) needs none of this — its
TLS handshake is genuine Chromium.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from ..core.errors import DependencyError
from .identity import NetworkIdentity

_NETWORK_EXTRA_HINT = 'SOCKS5 proxying requires the [network] extra. Install it with:\n    pip install "aetherius[network]"'


def httpx_proxy_kwargs(identity: NetworkIdentity) -> dict[str, Any]:
    """Keyword arguments for ``httpx.Client(...)`` implementing *identity*'s proxy (``{}`` if none)."""
    proxy = identity.proxy
    if proxy is None:
        return {}
    if proxy.scheme == "socks5" and importlib.util.find_spec("socksio") is None:
        raise DependencyError(_NETWORK_EXTRA_HINT, extra="network")
    return {"proxy": proxy.for_httpx()}


def impersonation_available() -> bool:
    """Whether the optional TLS-impersonation backend (``curl_cffi``) is importable."""
    return importlib.util.find_spec("curl_cffi") is not None
