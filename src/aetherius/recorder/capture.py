"""DOM capture data types shared by the Continuum backend and its tests.

The live-browser lifecycle now lives in the generic :mod:`.session`; this module holds the typed
representation of a captured DOM event and the parser that builds an element descriptor from the JSON
the in-page scripts report (:mod:`._capture_js`, :mod:`._overlay_js`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .selector_synth import Candidate, ElementDescriptor

# Overlay pick kinds, carrying an extraction/meta ``config`` rather than a plain action. ``finish`` is
# a control message handled by the backend (end the session), never turned into a recorded event.
_OVERLAY_KINDS = frozenset({"extract", "extract_records", "wait_for", "parameterize"})


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """One captured user action, before it is transformed into a Blueprint step.

    ``descriptor`` is the target element (the repeating container for records) or ``None`` for a
    navigation. A password field never carries its value: ``redacted`` is set instead. ``config``
    carries an overlay pick's details (name / as / attr / list / fields / input name).
    """

    kind: str  # navigate | click | fill | select | press | extract | extract_records | wait_for | parameterize
    descriptor: ElementDescriptor | None = None
    value: str | None = None
    key: str | None = None
    url: str | None = None
    redacted: bool = False
    config: dict[str, Any] | None = None
    ts: float = field(default_factory=time.monotonic)


def _descriptor_from_raw(raw: dict[str, Any]) -> ElementDescriptor:
    """Build an :class:`ElementDescriptor` from the JSON an in-page script sent."""
    candidates = tuple(
        Candidate(
            strategy=str(c["strategy"]),
            selector=str(c["selector"]),
            selector_type=str(c.get("selector_type", "css")),
            unique=bool(c["unique"]),
        )
        for c in raw.get("candidates", [])
    )
    return ElementDescriptor(
        tag=str(raw.get("tag", "")),
        css_path=str(raw.get("css_path", "")),
        candidates=candidates,
        text=raw.get("text"),
        name=raw.get("name"),
        field_type=raw.get("field_type"),
        autocomplete=raw.get("autocomplete"),
    )
