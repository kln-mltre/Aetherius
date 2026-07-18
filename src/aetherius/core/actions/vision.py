"""Vision actions: read (semantic extraction, Act III+).

Specs projected by the builder catalogue. The vision *targeting* of interactive actions
(click/type/upload/hover/wait_for with ``target: {vision: ...}``) is not a separate action — it is
an alternate target form on the interaction specs, resolved by the Oracle driver.
"""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "read",
        "Read data off the screen described in natural language (Act III+).",
        params=(
            ParamSpec(
                "vision",
                "string",
                required=True,
                help="Natural-language description of the data to read.",
                placeholder="the list of prices in the results table",
            ),
            ParamSpec(
                "schema",
                "object",
                help="JSON Schema of an object shaping the reply; omit for a free-form value "
                "returned under 'data'.",
                placeholder='{"type": "object", "properties": {"prices": {"type": "array"}}}',
            ),
        ),
    ),
)
