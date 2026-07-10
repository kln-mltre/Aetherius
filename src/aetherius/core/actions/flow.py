"""Control-flow actions: wait, wait_for, emit, if, repeat, for_each.

Specs projected by the builder catalogue. ``if``/``repeat``/``for_each`` are declared in the
capability table but not executed by any driver yet, so the builder marks them "not runnable yet";
their parameter shapes here are indicative and will firm up when a driver implements them.
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
        "Run nested steps conditionally (declared, not runnable yet).",
        params=(
            ParamSpec("condition", "string", help="Expression deciding the branch."),
            ParamSpec("then", "array", help="Steps to run when the condition holds."),
            ParamSpec("else", "array", help="Steps to run otherwise."),
        ),
    ),
    ActionSpec(
        "repeat",
        "Run nested steps a fixed number of times (declared, not runnable yet).",
        params=(
            ParamSpec("times", "integer", help="How many iterations."),
            ParamSpec("steps", "array", help="Steps to repeat."),
        ),
    ),
    ActionSpec(
        "for_each",
        "Run nested steps once per item (declared, not runnable yet).",
        params=(
            ParamSpec("items", "string", help="Expression yielding the items to iterate."),
            ParamSpec("as", "string", help="Loop variable name."),
            ParamSpec("steps", "array", help="Steps to run per item."),
        ),
    ),
)
