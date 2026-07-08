"""Blueprint recorder: launch a visible browser, capture a demonstration, emit a clean Blueprint.

Act-agnostic orchestrator: it picks the recorder backend for the requested Act (:mod:`.base`), drives
a generic :class:`~.session.RecordingSession`, assembles the backend's result into a Blueprint, and
re-validates the produced file through the canonical loader/validator — so the recorder can only ever
hand back a schema-valid, runnable Blueprint (or fail loudly). What is captured and how it maps to
steps is the backend's job (Continuum: DOM; Vector: network).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ..builder.factory import assemble_blueprint, slugify_name
from ..core.blueprint.loader import load_blueprint
from ..core.blueprint.validator import validate_for_act
from ..core.errors import BlueprintValidationError
from .base import get_recorder
from .session import NotifyCallback, RecordingSession

# assemble_blueprint is re-exported from builder.factory: Blueprint construction is the builder's
# job, and the recorder is one of its callers. Kept importable here for existing callers and tests.
__all__ = ["assemble_blueprint", "record_blueprint"]


def record_blueprint(
    name: str,
    start_url: str,
    *,
    act: str = "continuum",
    out_dir: Path | str | None = None,
    on_event: NotifyCallback | None = None,
    stop_event: threading.Event | None = None,
    credentials_as_secrets: bool = True,
) -> Path:
    """Record a demonstration for *act* in a live browser and write a validated Blueprint file.

    Returns the path of the written ``.blueprint.json`` (under *out_dir* or ``./blueprints/``).
    Raises :class:`~aetherius.core.errors.RecorderError` if *act* has no recorder backend, or
    :class:`BlueprintValidationError` if the assembled Blueprint fails canonical validation.
    """
    backend = get_recorder(act, credentials_as_secrets=credentials_as_secrets)
    session = RecordingSession(start_url, backend, on_event=on_event, stop_event=stop_event)
    result = session.record()

    description = (
        f"Genere par le recorder Aetherius (act {act}) a partir d'une demo sur {start_url}."
    )
    blueprint = assemble_blueprint(
        name,
        result.steps,
        result.secrets,
        act=act,
        inputs=result.inputs,
        outputs=result.outputs,
        description=description,
    )

    target_dir = Path(out_dir) if out_dir is not None else Path.cwd() / "blueprints"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{slugify_name(name)}.blueprint.json"
    path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        validate_for_act(load_blueprint(path))
    except Exception as exc:  # a produced-invalid Blueprint is our bug: surface it, do not hide it
        raise BlueprintValidationError(
            f"The recorder produced an invalid Blueprint: {exc}"
        ) from exc
    return path
