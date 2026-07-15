"""ProxyPool and rotation strategies.

Two real-world proxy shapes: a single rotating gateway (the provider rotates the exit IP behind one
endpoint) or a pool of endpoints Aetherius rotates itself. ``ProxyPool`` covers the pool case; a lone
gateway is just a pool of one. Rotation state (round-robin cursor, sticky map) can be persisted via
the store (Jalon A) for cross-run stickiness; a plain ``per_run`` rotation needs no persistence.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Literal

from ..core.errors import BlueprintValidationError
from .proxy import ProxySpec

RotationStrategy = Literal["per_run", "round_robin", "random", "sticky"]

_STRATEGIES = frozenset(("per_run", "round_robin", "random", "sticky"))


def _stable_index(key: str, modulo: int) -> int:
    """Deterministic index for *key*, independent of the process (unlike the salted ``hash()``)."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


@dataclass(slots=True)
class ProxyPool:
    """A set of proxies and how to pick one for a given run.

    Not frozen: ``round_robin`` advances an internal cursor. The cursor lives only for this pool
    instance, so cross-run sequential rotation needs the store; within a process it cycles evenly.
    ``per_run``/``random`` change the exit IP from one run to the next; ``sticky`` pins a proxy to a
    key (e.g. a Blueprint name) deterministically, surviving restarts without any persistence.
    """

    proxies: tuple[ProxySpec, ...]
    strategy: RotationStrategy = "per_run"
    _cursor: int = field(default=0, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.proxies:
            raise BlueprintValidationError("A proxy pool must contain at least one proxy.")
        if self.strategy not in _STRATEGIES:
            raise BlueprintValidationError(
                f"Unknown rotation strategy {self.strategy!r} (known: {sorted(_STRATEGIES)})."
            )

    def select(self, key: str | None = None) -> ProxySpec:
        """Pick a proxy per the strategy. ``key`` scopes stickiness (e.g. a schedule id)."""
        if len(self.proxies) == 1:
            return self.proxies[0]

        if self.strategy == "round_robin":
            proxy = self.proxies[self._cursor % len(self.proxies)]
            self._cursor += 1
            return proxy
        if self.strategy == "sticky" and key is not None:
            return self.proxies[_stable_index(key, len(self.proxies))]
        # per_run, random, or sticky without a key: a fresh pick each run.
        return random.choice(self.proxies)
