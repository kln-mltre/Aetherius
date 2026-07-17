"""Optional local cognition provider: on-device grounding (ONNX / local VLM), no external call.

Behind the same ``Grounder`` interface as the Claude default — this is where the original Oracle
"train a small model" idea lives on, now optional (extra ``[vision]``: onnxruntime/opencv). Model
assets are resolved and cached by ``models/registry.py``; ``onnxruntime``/``cv2`` are imported
lazily. Skeleton for Jalon 2-A; the local path is an advanced opt-in (see ``training/README.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._perception import Perception
    from .provider import GroundResult


class LocalGrounder:
    """Locate elements with an on-device detector. Implements ``Grounder`` only."""

    name = "local"

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def locate(self, perception: "Perception", description: str) -> "GroundResult":
        raise NotImplementedError("Local ONNX/VLM grounding is an optional path (Jalon 2-B+).")
