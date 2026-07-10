"""Tests for console/screenshots.py — the doc screenshot generator.

Doubles as a smoke test that every Console screen renders headlessly without error, and guards the
two properties the committed assets rely on: valid SVG, and deterministic/leak-free output (no random
Rich id, no absolute checkout path).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aetherius.console.screenshots import _REPO, _SHOTS, capture_all

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_capture_all_writes_one_valid_svg_per_shot(tmp_path: Path) -> None:
    paths = await capture_all(tmp_path)

    assert len(paths) == len(_SHOTS)
    slugs = {slug for slug, _, _ in _SHOTS}
    assert {p.stem for p in paths} == slugs

    for path in paths:
        svg = path.read_text(encoding="utf-8")
        assert svg.lstrip().startswith("<svg"), f"{path.name} is not an SVG"
        # Deterministic: the random Rich terminal id must have been normalised away.
        assert not re.search(r"terminal-\d+", svg), f"{path.name} keeps a variable id"
        # No absolute checkout path (author username / machine) leaked into a committed asset.
        assert str(_REPO) not in svg, f"{path.name} leaks the repo path"
