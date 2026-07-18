"""Oracle locator: resolve a vision target description to on-screen coordinates.

Bridges a ``Target`` (vision form) and a ``Grounder``: given a ``Perception`` and the description,
returns the ``Box`` the stealth mouse acts on. The confidence floor and the off-center point
picking live here, so the driver stays a pure dispatcher.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.errors import CognitionError

if TYPE_CHECKING:
    from random import Random

    from ...core.runtime.selector import Box, Target
    from .._cognition.provider import Grounder
    from .._perception import Perception

# Below this confidence the grounder is essentially guessing: acting on its box would click a
# near-random point of the page. Overridable per step via ``min_confidence``.
DEFAULT_MIN_CONFIDENCE = 0.5

# Off-center band (fraction of the box, per axis) a humanized interaction lands in: never
# dead-center (a robot tell), never the edges (risk of missing the element). Same band as the
# locator-based stealth click (docs/stealth.md).
_OFFCENTER_BAND = (0.3, 0.7)


def locate(
    grounder: "Grounder",
    perception: "Perception",
    target: "Target",
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> "Box":
    """Resolve *target*'s vision description to a ``Box`` via *grounder*.

    Raises:
        CognitionError: the target carries no vision description, or the grounder's confidence
            is below *min_confidence* — the element is most likely not on screen (or the
            description too ambiguous to act on).
    """
    description = target.vision
    if not description:
        raise CognitionError("locate() requires a vision target (target: {vision: ...}).")
    result = grounder.locate(perception, description)
    if result.confidence < min_confidence:
        raise CognitionError(
            f"Grounder is not confident enough that {description!r} is on screen "
            f"(confidence {result.confidence:.2f} < {min_confidence:.2f})."
        )
    return result.box


def point_in_box(box: "Box", rng: "Random") -> tuple[float, float]:
    """Pick the point the stealth mouse aims at: off-center, within the 30-70% band of *box*."""
    low, high = _OFFCENTER_BAND
    x = box.x + box.width * rng.uniform(low, high)
    y = box.y + box.height * rng.uniform(low, high)
    return (x, y)
