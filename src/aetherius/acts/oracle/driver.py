"""Oracle driver (Act III): vision-guided targeting on scripted steps.

Extends Continuum — same browser, same stealth, same selector-based dispatch, all inherited — with
two overlays resolved through the cognition substrate: interactive steps aiming at a
``target: {vision: "..."}`` (grounded to viewport coordinates, acted on through the stealth
humanizer) and the semantic ``read`` action (Extractor). One model call per targeted step: Oracle
never decides the flow, it only delegates target resolution, so a run stays scripted, auditable
and cheap — the deliberate contrast with Phantom (Act IV).
"""

from __future__ import annotations

import time
from random import Random
from typing import TYPE_CHECKING, Any, Callable, Mapping

from ...core.blueprint.models import StepModel
from ...core.errors import ActionError, StepTimeoutError
from ...core.events.bus import EventBus
from ...core.events.models import EventType, RunEvent
from ...core.runtime.context import RunContext
from ...core.runtime.selector import Box, Target
from ...models.registry import resolve_provider
from ...stealth.humanizer.input import HumanInput
from ...stealth.policy import OFF
from .._perception import capture
from ..continuum.bridge import failure_code
from ..continuum.browser import BrowserSession
from ..continuum.driver import ContinuumDriver
from .locator import DEFAULT_MIN_CONFIDENCE, locate, point_in_box

if TYPE_CHECKING:
    from .._cognition.provider import CognitionProvider

# Interactive actions that accept a vision target. Their selector form (and every other action)
# is inherited Continuum dispatch, untouched.
_VISION_ACTIONS: frozenset[str] = frozenset({"click", "type", "upload", "hover", "wait_for"})

# Each wait_for poll costs one grounding call: the interval balances reactivity against model
# spend (a 2.5 s cadence is plenty for "did the toast appear yet").
_WAIT_FOR_POLL_MS = 2500
_DEFAULT_TIMEOUT_MS = 30_000


def _wants_vision(params: Mapping[str, Any]) -> bool:
    """True when the step aims via ``target: {vision: ...}`` (drag's string target stays a selector)."""
    target = params.get("target")
    return isinstance(target, Mapping) and "vision" in target


class OracleDriver(ContinuumDriver):
    act = "oracle"

    def __init__(self) -> None:
        super().__init__()
        self._provider: "CognitionProvider | None" = None
        self._rng = Random()

    def setup(self, ctx: RunContext) -> None:
        super().setup(ctx)
        # Resolved after the browser starts so a bad vision config fails before any step runs;
        # the heavy SDK itself stays lazy (imported on the first model call).
        self._provider = resolve_provider(ctx.blueprint.vision)

    def run_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        if step.action == "read":
            return self._read(step, renderer)
        if step.action in _VISION_ACTIONS and _wants_vision(step.extra_fields):
            return self._vision_step(step, ctx, bus, renderer)
        return super().run_step(step, ctx, bus, renderer)

    # ── Vision path ──────────────────────────────────────────────────────────

    def _vision_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        session, provider = self._ready()
        params = step.extra_fields
        # from_step validates the authoring surface (ambiguous selector+vision, empty target).
        description = str(renderer(Target.from_step(params).vision))
        min_confidence = float(renderer(params.get("min_confidence", DEFAULT_MIN_CONFIDENCE)))

        if step.action == "wait_for":
            return self._wait_for_vision(step, ctx, bus, renderer, description, min_confidence)

        box = locate(
            provider,
            capture(session.page),
            Target(vision=description),
            min_confidence=min_confidence,
        )
        self._emit_grounded(ctx, bus, step, description, box)
        point = point_in_box(box, self._rng)
        human = self._human_input()

        match step.action:
            case "click":
                human.click_at(*point)
            case "hover":
                human.hover_at(*point)
            case "type":
                text = str(renderer(params.get("text", params.get("value", ""))))
                human.type_at(*point, text)
            case "upload":
                file = renderer(params.get("file", params.get("files")))
                if not file:
                    raise ActionError("upload requires a 'file'.")
                # A vision-targeted upload clicks the described control (dropzone, button) and
                # feeds the chooser that click opens — there is no file input to set directly.
                with session.page.expect_file_chooser() as chooser_info:
                    human.click_at(*point)
                chooser_info.value.set_files(file)
        return {}

    def _wait_for_vision(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
        description: str,
        min_confidence: float,
    ) -> dict[str, Any]:
        session, provider = self._ready()
        params = step.extra_fields
        default_ms = ctx.blueprint.options.timeout_ms or _DEFAULT_TIMEOUT_MS
        timeout_ms = float(renderer(params.get("timeout_ms", default_ms)))
        deadline = time.monotonic() + timeout_ms / 1000

        while True:
            result = provider.locate(capture(session.page), description)
            if result.confidence >= min_confidence:
                self._emit_grounded(ctx, bus, step, description, result.box)
                return {}
            # Below the floor means "not there yet", never an error: that is the whole point of
            # waiting. Only the deadline turns it into a failure.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                code = failure_code(renderer(params.get("on_timeout")))
                raise StepTimeoutError(
                    f"wait_for timed out for vision target {description!r} "
                    f"(last confidence {result.confidence:.2f} < {min_confidence:.2f})",
                    code=code,
                ) from None
            time.sleep(min(_WAIT_FOR_POLL_MS / 1000, remaining))

    # ── Semantic extraction ──────────────────────────────────────────────────

    def _read(self, step: StepModel, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        session, provider = self._ready()
        params = step.extra_fields
        description = renderer(params.get("vision", ""))
        if not description:
            raise ActionError("read requires a 'vision' description of the data to read.")
        schema = renderer(params.get("schema"))
        if schema is not None and not isinstance(schema, dict):
            raise ActionError("read: 'schema' must be an object (a JSON Schema).")

        data = provider.read(capture(session.page), str(description), schema=schema)
        if schema is not None and isinstance(data, dict):
            # The reply matches the caller's schema: expose its fields directly as the step's
            # outputs ({{ steps.x.<field> }}).
            return data
        return {"data": data}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _ready(self) -> tuple[BrowserSession, "CognitionProvider"]:
        if self._session is None or self._provider is None:
            raise ActionError("OracleDriver.run_step called before setup().")
        return self._session, self._provider

    def _human_input(self) -> HumanInput:
        session, _ = self._ready()
        if session.human is not None:
            return session.human
        # Stealth off: a plain facade over the current page — click_at/type_at degrade to raw
        # page.mouse operations, the same per-feature degradation as the rest of the humanizer.
        return HumanInput(session.page, self._policy or OFF)

    def _emit_grounded(
        self,
        ctx: RunContext,
        bus: EventBus,
        step: StepModel,
        description: str,
        box: Box,
    ) -> None:
        bus.emit(
            RunEvent(
                run_id=ctx.run_id,
                type=EventType.PROGRESS,
                step_id=step.id,
                message=f"vision: located {description!r}",
                level="debug",
                data={"box": {"x": box.x, "y": box.y, "width": box.width, "height": box.height}},
            )
        )
