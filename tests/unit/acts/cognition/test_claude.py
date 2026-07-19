"""Tests for acts/_cognition/claude.py — grounding and extraction with a mocked Anthropic client.

No network call is ever made: the client is replaced by a fake that records the request and
returns a canned response, so these tests assert the exact API shape (forced tool use, image
block, model selection) and the coordinate mapping back to CSS pixels.
"""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.cognition
anthropic = pytest.importorskip("anthropic")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from aetherius.acts._cognition.claude import ClaudeProvider, _png_size  # noqa: E402
from aetherius.acts._perception import Perception  # noqa: E402
from aetherius.acts.phantom.memory import AgentMemory  # noqa: E402
from aetherius.core.errors import CognitionError  # noqa: E402


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _perception(width: int = 640, height: int = 480) -> Perception:
    return Perception(screenshot=_png(width, height), viewport=(width, height), url="https://x")


class _FakeClient:
    """Records messages.create calls and replays a canned response."""

    def __init__(self, response: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self._response = response

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


def _tool_response(tool_input: dict[str, Any]) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=tool_input)], stop_reason="tool_use"
    )


def _provider(
    monkeypatch: pytest.MonkeyPatch, response: Any, *, model: str | None = None
) -> tuple[ClaudeProvider, _FakeClient]:
    client = _FakeClient(response)
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    return ClaudeProvider(model=model), client


def test_locate_builds_a_forced_grounding_call(monkeypatch: pytest.MonkeyPatch) -> None:
    box_reply = {"x": 100.0, "y": 80.0, "width": 120.0, "height": 40.0, "confidence": 0.92}
    provider, client = _provider(monkeypatch, _tool_response(box_reply))
    perception = _perception()

    result = provider.locate(perception, "the login button")

    assert (result.box.x, result.box.y) == (100.0, 80.0)
    assert (result.box.width, result.box.height) == (120.0, 40.0)
    assert result.confidence == 0.92

    call = client.calls[0]
    assert call["model"] == "claude-opus-4-8"  # default when vision.model is absent
    assert call["tool_choice"] == {"type": "tool", "name": "report_element"}
    assert call["tools"][0]["strict"] is True
    image_block, text_block = call["messages"][0]["content"]
    assert image_block["source"]["data"] == base64.standard_b64encode(perception.screenshot).decode(
        "ascii"
    )
    assert "the login button" in text_block["text"]


def test_locate_scales_the_box_back_after_downscaling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Long edge 5152 px is exactly twice the high-res limit: the image is halved before the
    # call, so model coordinates must be doubled to land back in CSS pixels.
    provider, client = _provider(
        monkeypatch,
        _tool_response({"x": 100, "y": 10, "width": 50, "height": 20, "confidence": 1.0}),
    )
    result = provider.locate(_perception(5152, 100), "a distant element")

    assert (result.box.x, result.box.y) == (200.0, 20.0)
    assert (result.box.width, result.box.height) == (100.0, 40.0)
    sent = base64.standard_b64decode(client.calls[0]["messages"][0]["content"][0]["source"]["data"])
    assert _png_size(sent) == (2576, 50)


def test_locate_clamps_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(
        monkeypatch,
        _tool_response({"x": 0, "y": 0, "width": 1, "height": 1, "confidence": 1.4}),
    )
    assert provider.locate(_perception(), "x").confidence == 1.0


def test_locate_without_tool_use_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    refusal = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="cannot help")], stop_reason="refusal"
    )
    provider, _ = _provider(monkeypatch, refusal)
    with pytest.raises(CognitionError, match="no tool call"):
        provider.locate(_perception(), "anything")


def test_locate_with_unusable_box_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(monkeypatch, _tool_response({"x": 1, "confidence": 0.5}))
    with pytest.raises(CognitionError, match="not a usable box"):
        provider.locate(_perception(), "anything")


def test_read_with_schema_forces_that_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    schema = {
        "type": "object",
        "properties": {"prices": {"type": "array", "items": {"type": "number"}}},
        "required": ["prices"],
    }
    provider, client = _provider(monkeypatch, _tool_response({"prices": [9.99, 4.5]}))

    data = provider.read(_perception(), "the list of prices", schema=schema)

    assert data == {"prices": [9.99, 4.5]}
    assert client.calls[0]["tools"][0]["input_schema"] is schema
    assert client.calls[0]["tool_choice"] == {"type": "tool", "name": "report_data"}


def test_read_without_schema_returns_the_free_form_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client = _provider(monkeypatch, _tool_response({"data": "In stock"}))
    assert provider.read(_perception(), "the availability label") == "In stock"
    assert client.calls[0]["tools"][0]["name"] == "report_data"


def test_vision_model_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, client = _provider(
        monkeypatch,
        _tool_response({"x": 0, "y": 0, "width": 1, "height": 1, "confidence": 1}),
        model="claude-sonnet-5",
    )
    provider.locate(_perception(), "x")
    assert client.calls[0]["model"] == "claude-sonnet-5"


# ── Planning (Phantom, Jalon 2-C) ─────────────────────────────────────────────


def _plan_response(name: str, tool_input: dict[str, Any]) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=name, input=tool_input)],
        stop_reason="tool_use",
    )


def _memory() -> AgentMemory:
    memory = AgentMemory(goal="find the first quote by Ada")
    memory.record({"action": "navigate", "url": "https://quotes.toscrape.com"}, {})
    return memory


def test_plan_forces_a_tool_and_offers_the_planner_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client = _provider(monkeypatch, _plan_response("click", {"target": "the Login link"}))

    action = provider.plan(
        "find the first quote by Ada", ["stay on the domain"], _perception(), _memory()
    )

    assert action == {"action": "click", "target": {"vision": "the Login link"}}
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "any"}
    names = {t["name"] for t in call["tools"]}
    assert {"navigate", "click", "type", "read", "finish", "abort"} <= names
    assert "find the first quote by Ada" in call["system"]
    assert "stay on the domain" in call["system"]
    # The current perception (screenshot) and the memory transcript are both in the user turn.
    content = call["messages"][0]["content"]
    assert any(block.get("type") == "image" for block in content)
    assert any("quotes.toscrape.com" in block.get("text", "") for block in content)


def test_plan_maps_the_finish_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(
        monkeypatch, _plan_response("finish", {"result": {"quote": "hi", "author": "Ada"}})
    )
    action = provider.plan("g", [], _perception(), _memory())
    assert action == {"action": "finish", "result": {"quote": "hi", "author": "Ada"}}


def test_plan_maps_the_abort_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(monkeypatch, _plan_response("abort", {"reason": "captcha"}))
    action = provider.plan("g", [], _perception(), _memory())
    assert action == {"action": "abort", "reason": "captcha"}


def test_plan_maps_a_typed_action_with_text(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(
        monkeypatch, _plan_response("type", {"target": "the search box", "text": "Ada"})
    )
    action = provider.plan("g", [], _perception(), _memory())
    assert action == {"action": "type", "target": {"vision": "the search box"}, "text": "Ada"}


def test_plan_without_tool_use_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    refusal = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I refuse")], stop_reason="end_turn"
    )
    provider, _ = _provider(monkeypatch, refusal)
    with pytest.raises(CognitionError, match="no tool call"):
        provider.plan("g", [], _perception(), _memory())


def test_plan_uses_the_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, client = _provider(monkeypatch, _plan_response("back", {}), model="claude-fable-5")
    provider.plan("g", [], _perception(), _memory())
    assert client.calls[0]["model"] == "claude-fable-5"
