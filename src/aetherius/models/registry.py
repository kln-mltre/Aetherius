"""Resolve a Blueprint's ``vision`` config to a cognition provider, and cache local model assets.

``vision.provider`` selects the backend — ``claude`` (default, extra ``[cognition]``) or ``local``
(extra ``[vision]``, ONNX/VLM). ``vision.model`` names the *model*, not the backend: an Anthropic
model id for Claude, a local asset name (``nom@version``) for the local grounder. Resolution is
cheap and import-light — the heavy SDKs are only pulled in when a provider method actually runs.

``models/store/`` is reserved for the local path's downloaded, versioned assets; the download and
cache machinery lands with real local grounding (Jalon 2-B+). Training lives under ``training/``
and stays an optional/advanced path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from ..core.errors import CognitionError

if TYPE_CHECKING:
    from ..acts._cognition.provider import CognitionProvider


def resolve_provider(vision: Mapping[str, Any] | None) -> "CognitionProvider":
    """Build the cognition provider named by *vision* (default: Claude)."""
    config = vision or {}
    provider = config.get("provider", "claude")
    model = config.get("model")

    if provider == "claude":
        from ..acts._cognition.claude import ClaudeProvider

        return ClaudeProvider(model=model)
    if provider == "local":
        from ..acts._cognition.local import LocalGrounder

        return LocalGrounder(model=model)
    raise CognitionError(
        f"Unknown cognition provider {provider!r}; expected 'claude' (default) or 'local'."
    )
