"""NetworkIdentity: the resolved egress + geo for a run, and how it is resolved.

Resolution order: the Blueprint's ``options.proxy`` wins; otherwise the environment default/pool from
settings; otherwise no proxy. The result travels to both engines (Vector httpx, Continuum Playwright)
and drives geo-coherent fingerprint overrides and the WebRTC leak guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .geo import GeoHint
from .proxy import ProxySpec

_PENDING = "Jalon 1.5-G (network): identity resolution not implemented yet."


@dataclass(frozen=True, slots=True)
class NetworkIdentity:
    """The effective network identity for one run."""

    proxy: ProxySpec | None = None
    geo: GeoHint | None = None
    # TLS impersonation target for Vector (e.g. "chrome"); None keeps the stock httpx handshake.
    impersonate: str | None = None


def resolve_identity(option: Any, *, run_key: str | None = None) -> NetworkIdentity:
    """Resolve the effective identity from ``options.proxy`` and settings, for this run.

    ``run_key`` scopes rotation stickiness (e.g. a schedule id) when the strategy calls for it.
    """
    raise NotImplementedError(_PENDING)
