"""Scroll-scan grounding: find a vision target beyond the current viewport.

A person told to "click X" scrolls until X is visible; the scan gives Oracle the same reflex.
The current viewport is tried first — a visible target costs exactly one grounding call, like a
plain locate. Below the confidence floor, the page is scrolled downward viewport by viewport
(humanized eased scroll when discretion is on, a raw wheel otherwise) and re-grounded; a run that
started mid-page wraps to the top once the bottom is reached, so the whole page is seen. Every
attempt is one model call, so the total is hard-capped — the cost model stays "bounded and
predictable", never "search forever".
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from ...core.errors import CognitionError
from .._perception import capture

if TYPE_CHECKING:
    from ...core.runtime.selector import Box
    from ...stealth.humanizer.input import HumanInput
    from .._cognition.provider import Grounder

# Total grounding attempts (initial viewport + scroll steps): bounds the model spend on an
# element that is nowhere on the page. Eight looks cover ~6.6 viewport heights.
_MAX_ATTEMPTS = 8

# Fraction of the viewport height per scroll step: the overlap guarantees an element straddling
# two viewports is fully visible in at least one attempt.
_STEP_RATIO = 0.8

# Settle time after each scroll: rendering plus lazy-loaded content catching up.
_SETTLE_S = 0.3


def _metrics(page: Any) -> tuple[float, float, float]:
    """Current scroll offset, viewport height and document height, in CSS pixels."""
    m = page.evaluate(
        "() => ({y: window.scrollY, vh: window.innerHeight,"
        " h: document.documentElement.scrollHeight})"
    )
    return float(m["y"]), float(m["vh"]), float(m["h"])


def _scroll_down(page: Any, human: "HumanInput | None", amount: float) -> None:
    if human is not None:
        human.scroll_by(amount)
    else:
        page.mouse.wheel(0, amount)


def ground_scanning(
    page: Any,
    human: "HumanInput | None",
    grounder: "Grounder",
    description: str,
    *,
    min_confidence: float,
    sleep: Callable[[float], None] = time.sleep,
) -> "Box":
    """Ground *description* on *page*, scrolling until it is seen or the page is exhausted.

    Raises:
        CognitionError: the element was not seen anywhere with enough confidence, with the
            number of looks and the best confidence observed — actionable either way (fix the
            description, or accept the element is absent).
    """
    start_y, _, _ = _metrics(page)
    wrapped = False  # becomes True after the jump back to the top of a mid-page start
    best = 0.0
    attempts = 0

    while attempts < _MAX_ATTEMPTS:
        attempts += 1
        result = grounder.locate(capture(page), description)
        if result.confidence >= min_confidence:
            return result.box
        best = max(best, result.confidence)

        y, vh, h = _metrics(page)
        if y + vh < h - 1:  # not at the bottom yet
            if wrapped and y >= start_y:
                break  # back around to the starting region: the whole page has been seen
            _scroll_down(page, human, vh * _STEP_RATIO)
            sleep(_SETTLE_S)
        elif not wrapped and start_y > 0:
            # Bottom reached but the run started mid-page: jump back up to cover what was above.
            wrapped = True
            page.evaluate("() => window.scrollTo(0, 0)")
            sleep(_SETTLE_S)
        else:
            break  # bottom reached and nothing left above: the whole page has been seen

    raise CognitionError(
        f"Grounder did not see {description!r} anywhere on the page "
        f"(scanned in {attempts} looks, best confidence {best:.2f} < {min_confidence:.2f})."
    )
