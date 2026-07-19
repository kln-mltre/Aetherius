"""The Claude planner: turn a goal + current perception into the next concrete action.

Phantom's decision policy (Act IV) delegates here. One vision call per loop iteration, forced onto
a fixed tool vocabulary (``tool_choice: any``) so the model must answer with a structured action
instead of prose — the same discipline as the grounder/extractor in ``claude.py``.

The tool vocabulary is deliberately *narrower than the Blueprint action surface*: the planner aims
at elements by natural-language description only (never a CSS selector it would have to invent), and
gets no ``evaluate``/``http.request``/flow/notify. Two terminal tools bound the loop: ``finish``
(goal reached, its payload is the run result) and ``abort`` (goal impossible or a constraint
forbids continuing — a clean, explainable stop).

``anthropic``/``PIL`` stay lazy: this module is only imported from ``ClaudeProvider.plan`` at
runtime, and it reuses ``claude._prepare_image`` (already loaded by then), so ``import aetherius``
stays light.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ...core.errors import CognitionError
from .claude import _prepare_image

if TYPE_CHECKING:
    from .._perception import Perception

# One screenshot + a short transcript is enough context for a step; keep the budget modest so a
# long history never balloons a single planning call.
_MAX_TOKENS = 2048

_TARGET_PROP = {
    "target": {
        "type": "string",
        "description": "Natural-language description of the element to act on "
        "(e.g. 'the Login link in the top navigation').",
    }
}

# Each entry: the tool exposed to Claude, plus how its input maps to a concrete step dict. The
# vision target form (`target: {vision: ...}`) is identical to Oracle's, so the inherited Oracle
# dispatch resolves it with no special-casing.
_PLANNER_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "navigate",
        "description": "Load a URL in the browser.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The absolute URL to open."}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "back",
        "description": "Go back to the previous page in history.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "click",
        "description": "Click the element that best matches the description.",
        "input_schema": {
            "type": "object",
            "properties": _TARGET_PROP,
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "type",
        "description": "Click the described field to focus it, then type the given text.",
        "input_schema": {
            "type": "object",
            "properties": {
                **_TARGET_PROP,
                "text": {"type": "string", "description": "The text to type."},
            },
            "required": ["target", "text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "press",
        "description": "Press a single keyboard key (e.g. 'Enter', 'Escape', 'Tab').",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "The key name."}},
            "required": ["key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page vertically by a pixel amount (positive scrolls down).",
        "input_schema": {
            "type": "object",
            "properties": {"dy": {"type": "number", "description": "Vertical pixels to scroll."}},
            "required": ["dy"],
            "additionalProperties": False,
        },
    },
    {
        "name": "wait",
        "description": "Pause for a number of milliseconds, e.g. to let content load.",
        "input_schema": {
            "type": "object",
            "properties": {"ms": {"type": "number", "description": "Milliseconds to wait."}},
            "required": ["ms"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read",
        "description": "Read data off the current screen, described in natural language. Use this "
        "to gather the information the goal asks for before finishing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What to read (e.g. 'the first quote text and its author').",
                }
            },
            "required": ["description"],
            "additionalProperties": False,
        },
    },
    {
        "name": "finish",
        "description": "The goal is achieved. Report the result the goal asked for.",
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {"description": "The goal's result, shaped as JSON (any type)."}
            },
            "required": ["result"],
            "additionalProperties": False,
        },
    },
    {
        "name": "abort",
        "description": "The goal cannot be achieved, or a constraint forbids continuing. Stop.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the goal cannot be reached."}
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
)

# tool name -> builder turning its input into a leaf step dict the Oracle driver dispatches.
_TO_STEP: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "navigate": lambda i: {"action": "navigate", "url": i["url"]},
    "back": lambda i: {"action": "back"},
    "click": lambda i: {"action": "click", "target": {"vision": i["target"]}},
    "type": lambda i: {
        "action": "type",
        "target": {"vision": i["target"]},
        "text": i.get("text", ""),
    },
    "press": lambda i: {"action": "press", "key": i["key"]},
    "scroll": lambda i: {"action": "scroll", "dy": i.get("dy", 0)},
    "wait": lambda i: {"action": "wait", "ms": i.get("ms", 0)},
    "read": lambda i: {"action": "read", "vision": i["description"]},
}


def _system_prompt(goal: str, constraints: list[str]) -> str:
    lines = [
        "You are an autonomous web agent driving a real browser toward a goal.",
        "Each turn you see a screenshot of the current viewport and must call exactly one tool.",
        "Target elements by natural-language description (click/type/read); never by CSS selector.",
        "Gather what the goal asks for with `read`, then call `finish` with that result.",
        "Call `abort` if the goal is impossible or a constraint forbids continuing.",
        "",
        f"GOAL: {goal}",
    ]
    if constraints:
        lines.append("CONSTRAINTS (must be respected at all times):")
        lines.extend(f"- {c}" for c in constraints)
    return "\n".join(lines)


def _user_content(perception: "Perception", transcript: str) -> list[dict[str, Any]]:
    image_b64, _ = _prepare_image(perception.screenshot)
    history = f"Actions so far:\n{transcript}" if transcript else "No actions taken yet."
    url = f"Current URL: {perception.url}\n" if perception.url else ""
    return [
        {"type": "text", "text": history},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
        },
        {"type": "text", "text": f"{url}Choose the single next action toward the goal."},
    ]


def plan_once(
    client: Any,
    model: str,
    goal: str,
    constraints: list[str],
    perception: "Perception",
    transcript: str,
) -> dict[str, Any]:
    """One planning call: return the next leaf step dict, or a ``finish``/``abort`` marker.

    Raises:
        CognitionError: the model answered without calling a tool, or named an unknown one.
    """
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=_system_prompt(goal, constraints),
        tools=list(_PLANNER_TOOLS),
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": _user_content(perception, transcript)}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return _to_step(block.name, dict(block.input))
    raise CognitionError(
        f"Planner returned no tool call (stop_reason={response.stop_reason!r}); "
        "cannot decide the next action."
    )


def _to_step(name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Map a chosen tool to its step dict; the terminal tools pass through as markers."""
    if name == "finish":
        return {"action": "finish", "result": params.get("result")}
    if name == "abort":
        return {"action": "abort", "reason": str(params.get("reason", "") or "")}
    builder = _TO_STEP.get(name)
    if builder is None:
        raise CognitionError(f"Planner chose an unknown tool {name!r}.")
    return builder(params)
