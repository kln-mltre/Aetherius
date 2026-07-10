"""Interaction actions: click, fill, type, press, select, hover, scroll, upload, drag.

Specs projected by the builder catalogue. Parameter names mirror the Playwright page operations in
``acts/continuum/actions.py`` exactly, so the forms produce steps the driver runs unchanged.
"""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

# Selector-based actions share these two parameters; declared once to stay in sync.
_SELECTOR = ParamSpec(
    "selector", "string", required=True, help="Target element selector.", placeholder="#submit"
)
_SELECTOR_TYPE = ParamSpec(
    "selector_type",
    "string",
    default="css",
    help="How to read 'selector': css (default), xpath or text.",
)

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec("click", "Click an element.", params=(_SELECTOR, _SELECTOR_TYPE)),
    ActionSpec(
        "fill",
        "Set an input's value in one shot (clears it first).",
        params=(
            _SELECTOR,
            ParamSpec(
                "value",
                "string",
                required=True,
                help="Value to set.",
                placeholder="{{ inputs.query }}",
            ),
            _SELECTOR_TYPE,
        ),
    ),
    ActionSpec(
        "type",
        "Type text character by character (for fields that react to each keystroke).",
        params=(
            _SELECTOR,
            ParamSpec("text", "string", required=True, help="Text to type."),
            ParamSpec("delay_ms", "number", help="Delay between keystrokes, in milliseconds."),
            _SELECTOR_TYPE,
        ),
    ),
    ActionSpec(
        "press",
        "Press a keyboard key, optionally focused on an element.",
        params=(
            ParamSpec("key", "string", required=True, help="Key name.", placeholder="Enter"),
            ParamSpec("selector", "string", help="Element to focus before pressing (optional)."),
            _SELECTOR_TYPE,
        ),
    ),
    ActionSpec(
        "select",
        "Choose one or more options in a <select> element.",
        params=(
            _SELECTOR,
            ParamSpec(
                "values",
                "array",
                required=True,
                help="Option value(s) to select.",
                placeholder='["option-1"]',
            ),
            _SELECTOR_TYPE,
        ),
    ),
    ActionSpec("hover", "Move the pointer over an element.", params=(_SELECTOR, _SELECTOR_TYPE)),
    ActionSpec(
        "scroll",
        "Scroll an element into view, or scroll the page by a delta.",
        params=(
            ParamSpec("selector", "string", help="Element to scroll into view (optional)."),
            ParamSpec("dx", "number", help="Horizontal wheel delta when no selector is given."),
            ParamSpec("dy", "number", help="Vertical wheel delta when no selector is given."),
            _SELECTOR_TYPE,
        ),
    ),
    ActionSpec(
        "upload",
        "Set the file(s) of a file input.",
        params=(
            _SELECTOR,
            ParamSpec(
                "file",
                "string",
                required=True,
                help="Path to the file to upload.",
                placeholder="{{ inputs.video }}",
            ),
            _SELECTOR_TYPE,
        ),
    ),
    ActionSpec(
        "drag",
        "Drag one element onto another.",
        params=(
            ParamSpec("source", "string", required=True, help="Selector to drag from."),
            ParamSpec("target", "string", required=True, help="Selector to drop onto."),
        ),
    ),
)
