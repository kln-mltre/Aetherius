"""Capability enum and ACT_CAPABILITIES map: the authoritative action/Act compatibility table."""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    # ── Act I — Vector ──────────────────────────────────────────────────────────
    HTTP_REQUEST = "http.request"
    SET = "set"
    ASSERT = "assert"
    EMIT = "emit"
    WAIT = "wait"

    # ── Act II — Continuum (browser) ─────────────────────────────────────────
    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    RELOAD = "reload"
    CLICK = "click"
    FILL = "fill"
    TYPE = "type"
    PRESS = "press"
    SELECT = "select"
    HOVER = "hover"
    SCROLL = "scroll"
    UPLOAD = "upload"
    DRAG = "drag"
    SCREENSHOT = "screenshot"
    EVALUATE = "evaluate"
    WAIT_FOR = "wait_for"

    # ── Flow (all Acts) ──────────────────────────────────────────────────────
    IF = "if"
    REPEAT = "repeat"
    FOR_EACH = "for_each"

    # ── Extract (all Acts) ───────────────────────────────────────────────────
    EXTRACT = "extract"


_VECTOR_CAPS: frozenset[Capability] = frozenset(
    {
        Capability.HTTP_REQUEST,
        Capability.SET,
        Capability.ASSERT,
        Capability.EMIT,
        Capability.WAIT,
        Capability.IF,
        Capability.FOR_EACH,
        Capability.EXTRACT,
    }
)

_CONTINUUM_CAPS: frozenset[Capability] = _VECTOR_CAPS | frozenset(
    {
        Capability.NAVIGATE,
        Capability.BACK,
        Capability.FORWARD,
        Capability.RELOAD,
        Capability.CLICK,
        Capability.FILL,
        Capability.TYPE,
        Capability.PRESS,
        Capability.SELECT,
        Capability.HOVER,
        Capability.SCROLL,
        Capability.UPLOAD,
        Capability.DRAG,
        Capability.SCREENSHOT,
        Capability.EVALUATE,
        Capability.WAIT_FOR,
        Capability.REPEAT,
    }
)

ACT_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "vector": _VECTOR_CAPS,
    "continuum": _CONTINUUM_CAPS,
    # Oracle and Phantom inherit all Continuum capabilities plus vision-specific ones.
    "oracle": _CONTINUUM_CAPS,
    "phantom": _CONTINUUM_CAPS,
}


# Actions listed in ACT_CAPABILITIES but not yet dispatched by the Act's driver: declaring them
# keeps the capability table forward-looking, but the builder must flag them "not runnable yet".
# ``extract`` (vector) is implemented inside ``http.request`` rather than as a standalone step;
# ``http.request`` (continuum) is inherited from the vector capability set but the browser driver
# does not run it yet. Guarded by tests/unit/acts/test_action_dispatch.py, which fails the moment a
# declared capability is neither dispatched nor listed here; shrink each entry as drivers catch up.
# Only runnable Acts appear (see IMPLEMENTED_ACTS).
PENDING_ACTIONS: dict[str, frozenset[Capability]] = {
    "vector": frozenset({Capability.IF, Capability.FOR_EACH, Capability.EXTRACT}),
    "continuum": frozenset(
        {Capability.IF, Capability.FOR_EACH, Capability.REPEAT, Capability.HTTP_REQUEST}
    ),
}
