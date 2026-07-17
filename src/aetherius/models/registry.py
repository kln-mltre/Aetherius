"""Resolve a Blueprint's ``vision`` config to a cognition provider, and cache local model assets.

``vision.provider`` selects the backend — ``claude`` (default, extra ``[cognition]``) or ``local``
(extra ``[vision]``, ONNX/VLM). ``vision.model`` names the model id. Local assets are downloaded,
versioned and cached under ``models/store/``. Skeleton for Jalon 2-A; training of local models lives
under ``training/`` and is an optional/advanced path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from ..acts._cognition.provider import CognitionProvider


def resolve_provider(vision: Mapping[str, Any] | None) -> "CognitionProvider":
    """Build the cognition provider named by *vision* (default: Claude). Implemented in Jalon 2-A."""
    raise NotImplementedError
