"""StealthPolicy: the decoded, typed intent behind ``options.stealth``.

The Blueprint carries ``options.stealth`` as loosely-typed data (off, a preset name, or an inline
object) so the JSON Schema stays the single source of shape. This module turns that data into one
frozen policy object the browser Acts can query without re-parsing: which humanizer features are on
and which fingerprint profile to wear. ``build_policy`` is the only entry point; a no-op policy
(everything off) preserves the historical default behaviour exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from ..core.errors import BlueprintValidationError

MouseMode = Literal["off", "gestures"]
KeyboardMode = Literal["off", "human"]
ScrollMode = Literal["off", "eased"]

_MOUSE_MODES = frozenset(get_args(MouseMode))
_KEYBOARD_MODES = frozenset(get_args(KeyboardMode))
_SCROLL_MODES = frozenset(get_args(ScrollMode))
_KNOWN_KEYS = frozenset({"mouse", "keyboard", "scroll", "timing", "fingerprint", "user_agent"})


@dataclass(frozen=True, slots=True)
class StealthPolicy:
    """Which discretion features are active for a run. Immutable once assembled.

    ``mouse``/``keyboard``/``scroll`` gate the humanizers; ``distraction`` is the probability of an
    occasional idle pause; ``fingerprint`` names a profile (or ``None`` to keep Playwright's stock
    fingerprint); ``user_agent`` overrides the UA string alone. ``OFF`` is the identity policy: no
    feature touches the page.
    """

    mouse: MouseMode = "off"
    keyboard: KeyboardMode = "off"
    scroll: ScrollMode = "off"
    distraction: float = 0.0
    fingerprint: str | None = None
    user_agent: str | None = None

    @property
    def is_active(self) -> bool:
        """True when at least one feature would alter the browser or its inputs.

        ``user_agent`` is deliberately excluded: it is the one piece of discretion the embedded
        engine also honours, and there it changes the UA and nothing else. Counting it here would
        drag in the fingerprint patches on this engine only — the same Blueprint behaving
        differently on the two engines, which is precisely what the shared contract exists to
        prevent. The UA is applied from the context options instead.
        """
        return (
            self.mouse != "off"
            or self.keyboard != "off"
            or self.scroll != "off"
            or self.fingerprint is not None
        )


# Identity policy shared by every "off" path, so callers can compare against a single instance.
OFF = StealthPolicy()

# Named presets usable as ``"stealth": "<name>"``. Kept deliberately small; a preset is just a
# curated StealthPolicy so power users can still spell every field out inline.
_PRESETS: dict[str, StealthPolicy] = {
    "off": OFF,
    "human": StealthPolicy(
        mouse="gestures",
        keyboard="human",
        scroll="eased",
        distraction=0.1,
        fingerprint="chrome-desktop",
    ),
}


def preset_names() -> list[str]:
    """The stealth preset names usable as ``"stealth": "<name>"``, sorted. A public view of the
    preset table so the builder offers exactly what ``build_policy`` accepts, without duplicating it.
    """
    return sorted(_PRESETS)


def _fail(detail: str) -> BlueprintValidationError:
    return BlueprintValidationError(f"Invalid options.stealth: {detail}")


def _distraction(timing: Any) -> float:
    if timing is None:
        return 0.0
    if not isinstance(timing, dict):
        raise _fail("'timing' must be an object.")
    value = timing.get("distraction", 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail("'timing.distraction' must be a number between 0 and 1.")
    if not 0.0 <= value <= 1.0:
        raise _fail("'timing.distraction' must be between 0 and 1.")
    return float(value)


def _choice(value: Any, allowed: frozenset[str], field: str) -> str:
    if value is None:
        return "off"
    if value not in allowed:
        raise _fail(f"'{field}' must be one of {sorted(allowed)}, got {value!r}.")
    return str(value)


def build_policy(raw: Any) -> StealthPolicy:
    """Decode ``options.stealth`` into a :class:`StealthPolicy`.

    Accepts the three shapes the schema allows: ``None``/``"off"`` (no-op), a preset name, or an
    inline object. Anything else raises a typed :class:`BlueprintValidationError` rather than
    silently degrading, so a malformed Blueprint fails loud and early.
    """
    if raw is None:
        return OFF
    if isinstance(raw, str):
        preset = _PRESETS.get(raw)
        if preset is None:
            raise _fail(f"unknown preset {raw!r} (known: {sorted(_PRESETS)}).")
        return preset
    if not isinstance(raw, dict):
        raise _fail("expected 'off', a preset name, or an object.")

    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise _fail(f"unknown keys {sorted(unknown)} (allowed: {sorted(_KNOWN_KEYS)}).")

    fingerprint = raw.get("fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        raise _fail("'fingerprint' must be a profile name (string).")

    user_agent = raw.get("user_agent")
    if user_agent is not None and not isinstance(user_agent, str):
        raise _fail("'user_agent' must be a string.")

    return StealthPolicy(
        mouse=_choice(raw.get("mouse"), _MOUSE_MODES, "mouse"),  # type: ignore[arg-type]
        keyboard=_choice(raw.get("keyboard"), _KEYBOARD_MODES, "keyboard"),  # type: ignore[arg-type]
        scroll=_choice(raw.get("scroll"), _SCROLL_MODES, "scroll"),  # type: ignore[arg-type]
        distraction=_distraction(raw.get("timing")),
        fingerprint=fingerprint,
        user_agent=user_agent,
    )
