"""Claude-backed cognition provider (default): grounding, semantic extraction and planning.

Fills the roles of ``provider.py`` via the Anthropic API (vision + forced tool use, so every
answer comes back structured instead of parsed out of prose). ``anthropic`` and ``PIL`` (extra
``[cognition]``) are imported lazily inside the methods, never at module load, so
``import aetherius`` stays light. Grounding and extraction land here (Jalon 2-A); planning lands
with Phantom (Jalon 2-C/2-D).

Coordinates: perception screenshots are 1 image pixel = 1 CSS pixel (see ``_perception``). Claude
returns boxes in pixels of the image it saw; when the screenshot exceeds the model's high-res
limit it is downscaled first and the box is scaled back, so callers always get viewport CSS px.
"""

from __future__ import annotations

import base64
import struct
from typing import TYPE_CHECKING, Any

from ...config.secrets import load_dotenv_once
from ...core.errors import CognitionError, DependencyError
from ...core.runtime.selector import Box
from .provider import GroundResult

if TYPE_CHECKING:
    from .._perception import Perception

_DEFAULT_MODEL = "claude-opus-4-8"

# High-resolution vision limit (long edge, px) on the default model: images beyond it are resized
# server-side, which would silently break the pixel-coordinate mapping. We downscale client-side
# instead and keep the factor, so returned boxes can be mapped back exactly.
_MAX_LONG_EDGE = 2576

_GROUND_TOOL = {
    "name": "report_element",
    "description": (
        "Report the bounding box of the single UI element that best matches the description, "
        "in pixels of the provided screenshot."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "number", "description": "Left edge of the element, in pixels."},
            "y": {"type": "number", "description": "Top edge of the element, in pixels."},
            "width": {"type": "number", "description": "Element width, in pixels."},
            "height": {"type": "number", "description": "Element height, in pixels."},
            "confidence": {
                "type": "number",
                "description": "How confident the match is, from 0 (guess) to 1 (certain).",
            },
        },
        "required": ["x", "y", "width", "height", "confidence"],
        "additionalProperties": False,
    },
}

# Fallback extraction tool when the caller gives no schema: a single free-form JSON value.
_READ_TOOL = {
    "name": "report_data",
    "description": "Report the data read off the screenshot, as a single JSON value.",
    "input_schema": {
        "type": "object",
        "properties": {"data": {"description": "The requested data, shaped as JSON."}},
        "required": ["data"],
        "additionalProperties": False,
    },
}


def _png_size(png: bytes) -> tuple[int, int]:
    """Width/height of a PNG from its IHDR header (always the first chunk, per the PNG spec)."""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise CognitionError("Perception screenshot is not a valid PNG.")
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def _prepare_image(png: bytes) -> tuple[str, float]:
    """Base64-encode *png* for the API, downscaling beyond the high-res limit.

    Returns ``(base64_data, scale)`` where ``scale`` is image px per CSS px — divide model
    coordinates by it to get back to the viewport. ``PIL`` is only touched on the resize path,
    which viewport-sized screenshots never hit.
    """
    width, height = _png_size(png)
    long_edge = max(width, height)
    if long_edge <= _MAX_LONG_EDGE:
        return base64.standard_b64encode(png).decode("ascii"), 1.0

    import io

    from PIL import Image

    scale = _MAX_LONG_EDGE / long_edge
    with Image.open(io.BytesIO(png)) as image:
        resized = image.resize((round(width * scale), round(height * scale)))
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode("ascii"), scale


class ClaudeProvider:
    """Default cognition provider. One instance per run; ``model`` comes from ``vision.model``."""

    name = "claude"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or _DEFAULT_MODEL
        self._client: Any = None

    def locate(self, perception: "Perception", description: str) -> GroundResult:
        prompt = (
            f"Locate the UI element matching this description: {description!r}. "
            "Report its bounding box in pixels of the screenshot via the report_element tool."
        )
        params, scale = self._request_tool(perception, prompt, _GROUND_TOOL, max_tokens=1024)
        try:
            box = Box(
                x=float(params["x"]) / scale,
                y=float(params["y"]) / scale,
                width=float(params["width"]) / scale,
                height=float(params["height"]) / scale,
            )
            confidence = min(1.0, max(0.0, float(params["confidence"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise CognitionError(f"Grounding reply is not a usable box: {params!r}") from exc
        return GroundResult(box=box, confidence=confidence)

    def read(
        self, perception: "Perception", description: str, *, schema: dict[str, Any] | None = None
    ) -> Any:
        if schema is not None:
            tool: dict[str, Any] = {
                "name": "report_data",
                "description": "Report the data read off the screenshot, matching the schema.",
                "input_schema": schema,
            }
            prompt = (
                f"Read the following off the screenshot: {description}. "
                "Report it via the report_data tool, matching its schema exactly."
            )
            params, _ = self._request_tool(perception, prompt, tool, max_tokens=4096)
            return params
        prompt = (
            f"Read the following off the screenshot: {description}. "
            "Report it via the report_data tool as a single JSON value."
        )
        params, _ = self._request_tool(perception, prompt, _READ_TOOL, max_tokens=4096)
        return params.get("data")

    def plan(
        self,
        goal: str,
        constraints: list[str],
        perception: "Perception",
        memory: Any,
    ) -> dict[str, Any] | None:
        # The planner tool table and message shaping live in planning.py (imported lazily so it
        # only loads on the Phantom path). It reuses this provider's client and model, so
        # vision.model selects the planner model too.
        from .planning import plan_once

        transcript = memory.transcript() if memory is not None else ""
        return plan_once(self._get_client(), self._model, goal, constraints, perception, transcript)

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise DependencyError(
                    "The Claude cognition provider requires the [cognition] extra "
                    "(pip install aetherius[cognition]).",
                    extra="cognition",
                ) from exc
            # The key may live in the developer's git-ignored .env (ANTHROPIC_API_KEY): load it
            # into the environment once so the zero-arg client resolves it like any env var.
            load_dotenv_once()
            self._client = anthropic.Anthropic()
        return self._client

    def _request_tool(
        self, perception: "Perception", prompt: str, tool: dict[str, Any], *, max_tokens: int
    ) -> tuple[dict[str, Any], float]:
        """One vision call with a forced tool: returns the tool input and the image scale."""
        image_b64, scale = _prepare_image(perception.screenshot)
        response = self._get_client().messages.create(
            model=self._model,
            max_tokens=max_tokens,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        for block in response.content:
            if block.type == "tool_use":
                return dict(block.input), scale
        raise CognitionError(
            f"Model returned no tool call (stop_reason={response.stop_reason!r}); "
            "cannot ground or extract from this reply."
        )
