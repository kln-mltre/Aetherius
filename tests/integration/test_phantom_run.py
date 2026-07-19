"""Integration: a full Phantom (Act IV) goal run through the engine against real Chromium.

The cognition provider is faked (no network, no [cognition] extra): its ``plan`` scripts a short
perceive->reason->act sequence and its ``locate``/``read`` stand in for a real grounder/extractor.
What this proves is the whole wiring — engine goal-seam -> PhantomDriver.run_goal -> loop ->
inherited Oracle vision dispatch on Continuum's real browser. The scripted click targets a real
anchor that changes the page URL, so the loop genuinely acted on the live page (the planner only
finishes once it observes the new URL). Marked ``browser``: skipped in base CI.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.integration]
pytest.importorskip("playwright")

from aetherius.acts._cognition.provider import GroundResult  # noqa: E402
from aetherius.acts._perception import Perception  # noqa: E402
from aetherius.core.blueprint.models import Blueprint  # noqa: E402
from aetherius.core.runtime.engine import RunEngine  # noqa: E402
from aetherius.core.runtime.result import RunStatus  # noqa: E402
from aetherius.core.runtime.selector import Box  # noqa: E402

# Clicking "Go" navigates to a second, distinctly-marked page — the observable, real browser side
# effect the agent must produce (via the vision-grounded click) before it can finish.
_SECOND_PAGE = "data:text/html," + urllib.parse.quote(
    "<!doctype html><title>SECOND-PAGE</title><body>done</body>"
)
_PAGE_HTML = (
    "<!doctype html><html><body>"
    f"<button onclick=\"location.assign('{_SECOND_PAGE}')\""
    ' style="position:fixed;left:100px;top:80px;width:120px;height:40px">Go</button>'
    "</body></html>"
)
_PAGE_URL = "data:text/html," + urllib.parse.quote(_PAGE_HTML)

_GO_BOX = Box(x=100, y=80, width=120, height=40)


class _ScriptedProvider:
    """A fake cognition provider: fixed grounding box, URL-reading extractor, scripted planner."""

    name = "fake"

    def __init__(self) -> None:
        self.plan_calls = 0
        self.last_read: Any = None

    def locate(self, perception: Perception, description: str) -> GroundResult:
        return GroundResult(box=_GO_BOX, confidence=0.99)

    def read(
        self, perception: Perception, description: str, *, schema: dict[str, Any] | None = None
    ) -> Any:
        # Read the live browser state (the URL) so the observation reflects the real click.
        self.last_read = perception.url
        return perception.url

    def plan(
        self, goal: str, constraints: list[str], perception: Perception, memory: Any
    ) -> dict[str, Any] | None:
        self.plan_calls += 1
        if self.plan_calls == 1:
            return {"action": "navigate", "url": _PAGE_URL}
        if self.plan_calls == 2:
            return {"action": "click", "target": {"vision": "the Go button"}}
        if self.plan_calls == 3:
            return {"action": "read", "vision": "the current URL"}
        return {"action": "finish", "result": {"seen": self.last_read}}


def test_phantom_run_reaches_its_goal_through_the_agent_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _ScriptedProvider()
    monkeypatch.setattr("aetherius.acts.oracle.driver.resolve_provider", lambda vision: provider)

    blueprint = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t.phantom.integration",
            "act": "phantom",
            "goal": "click Go and report the resulting URL",
            "options": {"timeout_ms": 8000, "agent": {"max_steps": 8}},
        }
    )

    result = RunEngine().run(blueprint)

    assert result.status is RunStatus.SUCCESS
    # No declared outputs: the engine returns the agent outcome directly.
    assert result.outputs["steps_taken"] == 3
    # The vision-grounded click really navigated the live page to the second page.
    assert "SECOND-PAGE" in urllib.parse.unquote(result.outputs["result"]["seen"])
    # Three actions dispatched (navigate, click, read) before finish.
    assert [r.step_id for r in result.step_results] == ["agent[0]", "agent[1]", "agent[2]"]
    assert all(r.status is RunStatus.SUCCESS for r in result.step_results)


def test_phantom_run_aborts_cleanly_when_the_planner_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Aborter(_ScriptedProvider):
        def plan(self, goal, constraints, perception, memory):  # type: ignore[override]
            if self.plan_calls == 0:
                self.plan_calls += 1
                return {"action": "navigate", "url": _PAGE_URL}
            return {"action": "abort", "reason": "the goal cannot be achieved here"}

    provider = _Aborter()
    monkeypatch.setattr("aetherius.acts.oracle.driver.resolve_provider", lambda vision: provider)

    blueprint = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t.phantom.abort",
            "act": "phantom",
            "goal": "do the impossible",
            "options": {"timeout_ms": 8000},
        }
    )

    result = RunEngine().run(blueprint)

    assert result.status is RunStatus.FAILED
    assert "aborted" in (result.error or "")
