"""Public surface of the package, and an executable guard for the "light import" invariant.

``import aetherius`` must stay cheap: the Act engines (Playwright, ONNX, OpenCV, Anthropic) are
heavy and optional, so importing the package must never pull them in. The last test enforces that in
a fresh interpreter, turning an architecture invariant into a regression test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import aetherius

pytestmark = pytest.mark.unit

# Heavy, optional Act dependencies that must not be imported by ``import aetherius``.
_HEAVY_MODULES = ("playwright", "onnxruntime", "cv2", "anthropic")


def test_public_surface() -> None:
    assert aetherius.__all__ == ["Aetherius", "__version__"]
    assert hasattr(aetherius, "Aetherius")


def test_run_raises_on_missing_file() -> None:
    from aetherius.core.errors import BlueprintLoadError

    with pytest.raises(BlueprintLoadError):
        aetherius.Aetherius().run("/nonexistent/blueprint.json")


def test_import_stays_lightweight() -> None:
    src = Path(__file__).resolve().parents[2] / "src"
    modules = ", ".join(repr(name) for name in _HEAVY_MODULES)
    code = (
        "import sys, aetherius; "
        f"leaked = [m for m in ({modules},) if m in sys.modules]; "
        "assert not leaked, leaked"
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(src), env.get("PYTHONPATH", "")]))
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
