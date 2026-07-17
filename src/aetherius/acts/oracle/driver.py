"""Oracle driver (Act III): vision-guided targeting on scripted steps.

Reuses Continuum's ``BrowserSession`` and stealth layer (same browser, same discretion) and resolves
a step's ``target: {vision: "..."}`` to on-screen coordinates via a cognition ``Grounder``, then acts
by coordinate through the stealth humanizer (``HumanInput.click_at``). Also runs the semantic
``read`` action via the ``Extractor``.

Not yet wired into ``RunEngine._make_driver`` — implemented in Jalon 2-B
(docs/phase-2/2-b-oracle.md). This is the interface skeleton.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .._shared import SharedActionsMixin

if TYPE_CHECKING:
    from ...core.blueprint.models import StepModel
    from ...core.events.bus import EventBus
    from ...core.runtime.context import RunContext


class OracleDriver(SharedActionsMixin):
    act = "oracle"

    def setup(self, ctx: "RunContext") -> None:
        raise NotImplementedError("Jalon 2-B (docs/phase-2/2-b-oracle.md).")

    def teardown(self, ctx: "RunContext") -> None:
        raise NotImplementedError("Jalon 2-B (docs/phase-2/2-b-oracle.md).")

    def run_step(
        self,
        step: "StepModel",
        ctx: "RunContext",
        bus: "EventBus",
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        raise NotImplementedError("Jalon 2-B (docs/phase-2/2-b-oracle.md).")
