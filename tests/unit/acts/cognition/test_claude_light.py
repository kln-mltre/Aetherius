"""Tests for the extra-free surface of acts/_cognition/claude.py.

Importing the module and parsing PNG geometry must work without anthropic/PIL installed; and
when the extra is genuinely absent, using the provider must fail with the typed DependencyError
(not a bare ImportError). The mocked API-call tests live in test_claude.py, under the
``cognition`` marker.
"""

from __future__ import annotations

import importlib.util
import struct

import pytest

from aetherius.acts._cognition.claude import ClaudeProvider, _png_size
from aetherius.acts._perception import Perception
from aetherius.core.errors import CognitionError, DependencyError

pytestmark = pytest.mark.unit

_ANTHROPIC_INSTALLED = importlib.util.find_spec("anthropic") is not None


def _png_header(width: int, height: int) -> bytes:
    """A minimal PNG prefix: signature + IHDR chunk header + dimensions."""
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    )


def test_png_size_reads_ihdr_dimensions() -> None:
    assert _png_size(_png_header(640, 480)) == (640, 480)


def test_png_size_rejects_non_png_bytes() -> None:
    with pytest.raises(CognitionError, match="not a valid PNG"):
        _png_size(b"GIF89a not a png at all........")


@pytest.mark.skipif(_ANTHROPIC_INSTALLED, reason="only meaningful without the [cognition] extra")
def test_locate_without_extra_raises_typed_dependency_error() -> None:
    perception = Perception(screenshot=_png_header(640, 480), viewport=(640, 480))
    with pytest.raises(DependencyError) as excinfo:
        ClaudeProvider().locate(perception, "the login button")
    assert excinfo.value.extra == "cognition"
