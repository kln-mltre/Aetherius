"""Network identity for Aetherius (Phase 1.5, Jalon G).

Makes the bot invisible at the network layer, not just at the browser-fingerprint layer: route
traffic through proxies (HTTP/HTTPS/SOCKS5), rotate the exit IP per run (from a pool or a rotating
gateway), keep the browser fingerprint coherent with the exit IP's geography, prevent the WebRTC
real-IP leak, and optionally impersonate a browser's TLS handshake (JA3/JA4) for the Vector engine.

It applies to BOTH engines through a single top-level ``options.proxy`` option, since the stealth
layer only reaches the browser today. Basic HTTP/HTTPS proxying needs no extra dependency; SOCKS5 and
TLS impersonation live behind the optional ``[network]`` extra and are imported lazily.

Status: jalon en attente. The public shape is fixed here; the implementation lands with Jalon G.
See docs/phase-1.5/g-network.md.
"""

from __future__ import annotations

from .geo import GeoHint, geo_hint
from .identity import NetworkIdentity, resolve_identity
from .pool import ProxyPool, RotationStrategy
from .proxy import ProxySpec, parse_proxy
from .transport import httpx_proxy_kwargs, impersonation_available

__all__ = [
    "ProxySpec",
    "parse_proxy",
    "ProxyPool",
    "RotationStrategy",
    "GeoHint",
    "geo_hint",
    "NetworkIdentity",
    "resolve_identity",
    "httpx_proxy_kwargs",
    "impersonation_available",
]
