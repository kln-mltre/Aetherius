"""Aetherius: a fixed, robust web-bot engine driven by declarative instruction files (Blueprints).

Public surface. Heavy machinery lives in subpackages and is imported lazily so that
``import aetherius`` stays cheap and dependency-light. Blueprints are executed in-process
through the :class:`Aetherius` facade, or from any language through the local daemon.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from .version import __version__

if TYPE_CHECKING:
    from .core.runtime.result import Result

__all__ = ["Aetherius", "__version__"]


class Aetherius:
    """In-process entry point: load a Blueprint and run it.

    The facade is deliberately thin. It defers to ``aetherius.core.runtime`` for execution
    so that importing the package never pulls in Act-specific dependencies (Playwright, ONNX, …).
    """

    def run(
        self,
        blueprint: str,
        *,
        inputs: Mapping[str, Any] | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> "Result":
        """Execute a Blueprint file and return its :class:`~aetherius.core.runtime.result.Result`.

        ``blueprint`` is a path to a JSON or YAML instruction file; ``inputs`` fills its declared
        parameters and ``secrets`` provides runtime-only credentials that are never persisted.
        """
        from .core.blueprint.loader import load_blueprint
        from .core.runtime.engine import RunEngine

        return RunEngine().run(load_blueprint(blueprint), inputs=inputs, secrets=secrets)
