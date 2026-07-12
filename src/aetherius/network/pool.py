"""ProxyPool and rotation strategies.

Two real-world proxy shapes: a single rotating gateway (the provider rotates the exit IP behind one
endpoint) or a pool of endpoints Aetherius rotates itself. ``ProxyPool`` covers the pool case; a lone
gateway is just a pool of one. Rotation state (round-robin cursor, sticky map) can be persisted via
the store (Jalon A) for cross-run stickiness; a plain ``per_run`` rotation needs no persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .proxy import ProxySpec

RotationStrategy = Literal["per_run", "round_robin", "random", "sticky"]

_PENDING = "Jalon 1.5-G (network): proxy pool rotation not implemented yet."


@dataclass(frozen=True, slots=True)
class ProxyPool:
    """A set of proxies and how to pick one for a given run."""

    proxies: tuple[ProxySpec, ...]
    strategy: RotationStrategy = "per_run"

    def select(self, key: str | None = None) -> ProxySpec:
        """Pick a proxy per the strategy. ``key`` scopes stickiness (e.g. a schedule id)."""
        raise NotImplementedError(_PENDING)
