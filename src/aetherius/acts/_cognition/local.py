"""Optional local cognition provider: on-device grounding (ONNX / local VLM), no external call.

Behind the same ``Grounder`` interface as the Claude default — this is where the original Oracle
"train a small model" idea lives on, now optional (extra ``[vision]``: onnxruntime/opencv). Model
assets are resolved and cached by ``models/registry.py``; ``onnxruntime``/``cv2`` are imported
lazily. The local path only grounds: ``read``/``plan`` exist so the class satisfies the full
``CognitionProvider`` protocol (keeping ``resolve_provider`` return type simple), but raise a
typed ``CognitionError`` — extraction and planning always need a full provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.errors import CognitionError

if TYPE_CHECKING:
    from .._perception import Perception
    from .provider import GroundResult


class LocalGrounder:
    """Locate elements with an on-device detector. Grounding only; other roles raise."""

    name = "local"

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def locate(self, perception: "Perception", description: str) -> "GroundResult":
        raise NotImplementedError("Local ONNX/VLM grounding is an optional path (Jalon 2-B+).")

    def read(
        self, perception: "Perception", description: str, *, schema: dict[str, Any] | None = None
    ) -> Any:
        raise CognitionError(
            "The local provider only grounds; use provider 'claude' for semantic extraction."
        )

    def plan(
        self,
        goal: str,
        constraints: list[str],
        perception: "Perception",
        memory: Any,
    ) -> dict[str, Any] | None:
        raise CognitionError("The local provider only grounds; use provider 'claude' for planning.")
