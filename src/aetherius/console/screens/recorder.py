"""Launch and drive the Blueprint recorder from the Console."""

from __future__ import annotations

from ._pending import PendingScreen


class RecorderScreen(PendingScreen):
    title_text = "Recorder"
    description_text = (
        "Will capture a browser demonstration and synthesize a clean Blueprint with robust "
        "selectors, instead of writing steps by hand."
    )
    milestone_text = "the recorder (src/aetherius/recorder/)."
