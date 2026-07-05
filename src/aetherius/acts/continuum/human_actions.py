"""Humanized variants of the interactive page actions, used when a StealthPolicy enables them.

The plain actions in ``actions.py`` stay the fast, deterministic default. When discretion is on, the
driver routes the interactive subset (click/hover/fill/type/scroll) here instead: same
``(params, render) -> dict`` contract, but the operation runs through :class:`HumanInput` so it is
paced and moved like a person. Locator resolution is reused from ``actions.py`` — this module owns
none of Playwright's selector logic, only the choice to humanize.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ...stealth.humanizer.input import HumanInput
from ...stealth.policy import StealthPolicy
from .actions import Renderer, _locator


def _target(human: HumanInput, params: Mapping[str, Any], render: Renderer) -> Any:
    return _locator(human.page, params, render)


def click(human: HumanInput, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    human.click(_target(human, params, render))
    return {}


def hover(human: HumanInput, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    human.hover(_target(human, params, render))
    return {}


def fill(human: HumanInput, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    human.fill(_target(human, params, render), render(params.get("value", "")))
    return {}


def type_text(human: HumanInput, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    text = render(params.get("text", params.get("value", "")))
    human.type(_target(human, params, render), text)
    return {}


def scroll(human: HumanInput, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    # A targeted scroll is about reaching an element (kept programmatic); a bare delta is a real
    # wheel gesture and gets the eased humanized motion.
    if params.get("selector"):
        _locator(human.page, params, render).scroll_into_view_if_needed()
    else:
        human.scroll_by(float(render(params.get("dy", 0)) or 0))
    return {}


HumanAction = Callable[[HumanInput, Mapping[str, Any], Renderer], dict[str, Any]]

HUMAN_ACTIONS: dict[str, HumanAction] = {
    "click": click,
    "hover": hover,
    "fill": fill,
    "type": type_text,
    "scroll": scroll,
}


def humanized_actions(policy: StealthPolicy) -> frozenset[str]:
    """Which action names *policy* should route to the humanized layer (empty when none apply)."""
    actions: set[str] = set()
    if policy.mouse == "gestures":
        actions |= {"click", "hover", "fill", "type"}
    if policy.keyboard == "human":
        actions |= {"fill", "type"}
    if policy.scroll == "eased":
        actions |= {"scroll"}
    return frozenset(actions)
