"""UI-friendly metadata for Acts and actions, projected from the core action registry.

This is the projection the README calls the builder catalogue: it joins the capability table
(``core/actions/base.py``), the field specs (``core/actions/registry.action_specs``) and the
runnable-Act set (``IMPLEMENTED_ACTS``) into flat, Textual-free records the Console and the daemon
can render. No action metadata is defined here — only combined and ordered — so the registry stays
the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.actions.base import ACT_CAPABILITIES, PENDING_ACTIONS, Capability
from ..core.actions.registry import action_specs, plugin_actions
from ..core.actions.spec import ActionSpec
from ..core.errors import BuilderError
from ..core.runtime.engine import IMPLEMENTED_ACTS

# Canonical display order, escalating Act by Act.
_ACT_ORDER: tuple[str, ...] = ("vector", "continuum", "oracle", "phantom")

_ACT_TITLES: dict[str, str] = {
    "vector": "Vector — HTTP / API",
    "continuum": "Continuum — scripted browser",
    "oracle": "Oracle — vision-guided browser",
    "phantom": "Phantom — autonomous agent",
}

# One-line explanation shown next to each Act in the picker and the catalogue.
_ACT_SUMMARIES: dict[str, str] = {
    "vector": "HTTP/API requests. Fastest, no browser. The 'axios' case.",
    "continuum": "Scripted browser (Playwright): login, JS, session, DOM. Stable selectors.",
    "oracle": "Vision-guided browser with discretion. Locates fragile/obfuscated UI on screen.",
    "phantom": "Autonomous agent: perceive, reason, act in a loop. Unscripted goals.",
}


@dataclass(frozen=True)
class ActInfo:
    """An Act as the builder presents it: title, explanation, and whether it runs today."""

    act: str
    title: str
    summary: str
    implemented: bool


@dataclass(frozen=True)
class ActionInfo:
    """An action available under an Act, with its spec and whether that Act runs it yet."""

    spec: ActionSpec
    runnable: bool


def act_infos() -> list[ActInfo]:
    """Every Act in canonical order, with its runnable status from IMPLEMENTED_ACTS."""
    return [
        ActInfo(
            act=act,
            title=_ACT_TITLES[act],
            summary=_ACT_SUMMARIES[act],
            implemented=act in IMPLEMENTED_ACTS,
        )
        for act in _ACT_ORDER
    ]


def get_act_info(act: str) -> ActInfo:
    """Return the :class:`ActInfo` for *act* or raise :class:`BuilderError`."""
    if act not in _ACT_TITLES:
        raise BuilderError(f"Unknown act {act!r} (known: {list(_ACT_ORDER)}).")
    return next(info for info in act_infos() if info.act == act)


def actions_for_act(act: str) -> list[ActionInfo]:
    """The actions an *act* supports, sorted by name, each flagged runnable or pending.

    An action is runnable when its Act is implemented and the action is not in that Act's
    PENDING_ACTIONS set (declared in the capability table but not dispatched by a driver yet).
    Loaded plugin actions are act-agnostic (docs/plugins.md), so they appear under every Act,
    runnable wherever the Act itself is.
    """
    caps = ACT_CAPABILITIES.get(act)
    if caps is None:
        raise BuilderError(f"Unknown act {act!r} (known: {list(_ACT_ORDER)}).")
    specs = action_specs()
    pending: frozenset[Capability] = PENDING_ACTIONS.get(act, frozenset())
    implemented = act in IMPLEMENTED_ACTS
    infos = [
        ActionInfo(spec=specs[cap.value], runnable=implemented and cap not in pending)
        for cap in caps
    ]
    infos += [ActionInfo(spec=specs[name], runnable=implemented) for name in plugin_actions()]
    return sorted(infos, key=lambda info: info.spec.name)
