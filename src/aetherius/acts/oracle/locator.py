"""Oracle locator: resolve a vision target description to on-screen coordinates.

Bridges a ``Target`` (vision form) and a ``Grounder``: given a ``Perception`` and the description,
returns the ``Box`` whose centre the stealth mouse clicks. Skeleton for Jalon 2-B.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.runtime.selector import Box, Target
    from .._cognition.provider import Grounder
    from .._perception import Perception


def locate(grounder: "Grounder", perception: "Perception", target: "Target") -> "Box":
    """Resolve *target*'s vision description to a ``Box`` via *grounder*. Implemented in Jalon 2-B."""
    raise NotImplementedError
