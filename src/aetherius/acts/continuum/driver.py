"""Continuum driver: follows the Blueprint literally against a real browser page.

Act II. Dispatches each step to a Playwright page operation (actions.py), a DOM read
(bridge.py), an artifact producer (screenshot), or an Act-agnostic handler (SharedActionsMixin).
Synchronous throughout, matching the engine; Playwright is imported lazily by BrowserSession.
"""

from __future__ import annotations

from typing import Any, Callable

from .._shared import SharedActionsMixin
from ...core.blueprint.models import StepModel
from ...core.errors import ActionError
from ...core.events.bus import EventBus
from ...core.events.models import EventType, RunEvent
from ...core.runtime.context import RunContext
from ...stealth.policy import StealthPolicy, build_policy
from ...stealth.session.store import resolve_profile_dir, run_dir
from .actions import PAGE_ACTIONS, _locator
from .bridge import evaluate, extract, wait_for
from .browser import BrowserSession
from .human_actions import HUMAN_ACTIONS, humanized_actions


class ContinuumDriver(SharedActionsMixin):
    act = "continuum"

    def __init__(self) -> None:
        self._session: BrowserSession | None = None
        self._policy: StealthPolicy | None = None
        self._humanized: frozenset[str] = frozenset()

    def setup(self, ctx: RunContext) -> None:
        opts = ctx.blueprint.options
        session_opts = opts.session
        profile_dir = None
        if session_opts is not None and session_opts.persist:
            profile_dir = resolve_profile_dir(session_opts.profile)
        self._policy = build_policy(opts.stealth)
        self._humanized = humanized_actions(self._policy)
        self._session = BrowserSession(
            debug=opts.debug,
            timeout_ms=opts.timeout_ms or 30_000,
            profile_dir=profile_dir,
            stealth=self._policy,
        )
        self._session.start()

    def teardown(self, ctx: RunContext) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def run_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        if self._session is None:
            raise ActionError("ContinuumDriver.run_step called before setup().")
        page = self._session.page
        params = step.extra_fields

        human = self._session.human
        if human is not None and step.action in self._humanized:
            return HUMAN_ACTIONS[step.action](human, params, renderer)

        page_action = PAGE_ACTIONS.get(step.action)
        if page_action is not None:
            self._session.pace_raw_action()  # keep raw ops watchable in debug (slow_mo off here)
            return page_action(page, params, renderer)

        match step.action:
            case "extract":
                return extract(page, params, renderer)
            case "wait_for":
                return wait_for(page, params, renderer)
            case "evaluate":
                return evaluate(page, params, renderer)
            case "screenshot":
                return self._screenshot(step, ctx, bus, renderer)
            case "emit":
                return self._emit(step, ctx, bus, renderer)
            case "wait":
                if human is not None:
                    human.park()  # drift the cursor off the controls while idling, like a person
                return self._wait(step, renderer)
            case "set":
                return self._set(step, renderer)
            case "assert":
                return self._assert(step, renderer)
            case "notify":
                return self._notify(step, ctx, bus, renderer)
            case _:
                raise ActionError(f"ContinuumDriver: unsupported action {step.action!r}")

    def _screenshot(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        assert self._session is not None
        page = self._session.page
        params = step.extra_fields
        name = renderer(params.get("name")) or f"{step.id or 'screenshot'}.png"
        path = run_dir(ctx.run_id) / str(name)

        if params.get("selector"):
            _locator(page, params, renderer).screenshot(path=str(path))
        else:
            page.screenshot(
                path=str(path), full_page=bool(renderer(params.get("full_page", False)))
            )

        bus.emit(
            RunEvent(
                run_id=ctx.run_id,
                type=EventType.ARTIFACT,
                step_id=step.id,
                message=f"screenshot: {path}",
                level="info",
                data={"kind": "screenshot", "path": str(path)},
            )
        )
        return {"path": str(path)}
