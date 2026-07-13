"""Control-flow actions: wait, wait_for, emit, if, repeat, for_each.

Specs projected by the builder catalogue. ``if``/``repeat``/``for_each`` are interpreted by the
step executor (core/runtime/steps.py) for every Act, so they never reach a driver; their nested
step lists (``then``/``else``/``steps``) are formalised in contracts/blueprint.schema.json.
"""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "wait",
        "Pause for a fixed number of milliseconds.",
        params=(ParamSpec("ms", "number", help="Milliseconds to wait.", placeholder="1000"),),
    ),
    ActionSpec(
        "wait_for",
        "Block until a selector reaches a state (Act II).",
        params=(
            ParamSpec(
                "selector",
                "string",
                required=True,
                help="Selector to wait for.",
                placeholder=".results",
            ),
            ParamSpec(
                "state",
                "string",
                default="visible",
                help="Target state: visible, attached, hidden or detached.",
            ),
            ParamSpec("timeout_ms", "number", help="Give up after this many milliseconds."),
            ParamSpec(
                "on_timeout", "string", help="Named failure on timeout, e.g. 'fail:LOGIN_FAILED'."
            ),
        ),
    ),
    ActionSpec(
        "emit",
        "Emit a progress event with a message.",
        params=(
            ParamSpec("message", "string", help="Event message.", placeholder="LOGIN_SUCCESS"),
        ),
    ),
    ActionSpec(
        "if",
        "Run nested steps conditionally.",
        params=(
            ParamSpec("condition", "string", required=True, help="Expression deciding the branch."),
            ParamSpec(
                "then", "array", required=True, help="Steps to run when the condition holds."
            ),
            ParamSpec("else", "array", help="Steps to run otherwise."),
        ),
    ),
    ActionSpec(
        "repeat",
        "Run nested steps a fixed number of times.",
        params=(
            ParamSpec("times", "integer", required=True, help="How many iterations."),
            ParamSpec("steps", "array", required=True, help="Steps to repeat."),
        ),
    ),
    ActionSpec(
        "for_each",
        "Run nested steps once per item.",
        params=(
            ParamSpec(
                "items",
                "string",
                required=True,
                help="Expression yielding the list to iterate.",
            ),
            ParamSpec("as", "string", help="Loop variable name (default: item)."),
            ParamSpec("steps", "array", required=True, help="Steps to run per item."),
        ),
    ),
)
