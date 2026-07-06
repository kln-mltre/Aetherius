"""Recorder backends behind a common interface, selected by Act — a mirror of the driver pattern.

A recorder captures a demonstration in a live browser and turns it into a Blueprint. *How* it captures
and *what* it emits depends on the Act: Continuum records DOM interactions, Vector records network
calls. Both plug into the same generic browser shell (:mod:`.session`) through this interface, and the
registry maps ``act -> backend`` exactly as ``ACT_CAPABILITIES`` maps ``act -> capabilities``.

Acts without a recorder yet (Oracle, Phantom) are declared here as pending holes: asking for one
raises a clear :class:`RecorderError` instead of failing obscurely, so the CLI/Console can say so
honestly — the same "honest milestone" pattern used elsewhere (PendingScreen, DependencyError).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

from ..core.errors import RecorderError

if TYPE_CHECKING:
    from .session import RecordingSession

# Acts that are real Aetherius Acts but whose recorder is a later milestone (documented in
# docs/recorder.md). Kept distinct from a plainly unknown act so the message can be specific.
_PENDING_RECORDERS: dict[str, str] = {
    "oracle": "visual annotation (bounding boxes on screenshots) feeding training/",
    "phantom": "goal-based demonstration",
}

_BACKENDS: dict[str, Callable[..., "RecorderBackend"]] = {}


@dataclass
class RecordingResult:
    """What a backend produces from a session: the pieces of the Blueprint (minus the envelope)."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)


class RecorderBackend(Protocol):
    """One Act's way of recording. The generic session drives it through these three hooks."""

    act: str

    def init_scripts(self) -> list[str]:
        """Scripts to inject (``add_init_script``) into every document before the page runs."""
        ...

    def attach(self, session: "RecordingSession") -> None:
        """Register bindings and page hooks on *session* (called once the context exists)."""
        ...

    def result(self) -> RecordingResult:
        """Transform everything captured during the session into a RecordingResult."""
        ...


def register_backend(act: str, factory: Callable[..., "RecorderBackend"]) -> None:
    """Register a backend factory for *act* (called at backend-module import).

    The factory accepts arbitrary keyword options and picks the ones its Act understands, so
    ``get_recorder`` can forward Act-specific knobs (e.g. ``credentials_as_secrets``) uniformly.
    """
    _BACKENDS[act] = factory


def _ensure_loaded() -> None:
    """Import the backend modules so their registrations run (idempotent, dependency-light)."""
    from . import continuum_backend, vector_backend  # noqa: F401  (import for side effects)


def get_recorder(act: str, **options: Any) -> "RecorderBackend":
    """Return a fresh backend for *act* (forwarding *options*), or raise a clear RecorderError."""
    _ensure_loaded()
    factory = _BACKENDS.get(act)
    if factory is not None:
        return factory(**options)
    if act in _PENDING_RECORDERS:
        raise RecorderError(
            f"The recorder for act {act!r} is a pending milestone "
            f"({_PENDING_RECORDERS[act]}); see docs/recorder.md."
        )
    raise RecorderError(f"Unknown act {act!r} (no recorder backend).")


def recorder_acts() -> set[str]:
    """Acts that have a working recorder today (single source of truth, like IMPLEMENTED_ACTS)."""
    _ensure_loaded()
    return set(_BACKENDS)
