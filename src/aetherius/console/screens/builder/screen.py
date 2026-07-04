"""Blueprint Studio orchestrator screen."""

from __future__ import annotations

from .._pending import PendingScreen


class BlueprintStudioScreen(PendingScreen):
    title_text = "Blueprint Studio"
    description_text = (
        "Will let you pick an Act and assemble a Blueprint's steps through forms, with a live "
        "JSON preview validated against the schema — no hand-written JSON required."
    )
    milestone_text = "the headless builder (src/aetherius/builder/)."
