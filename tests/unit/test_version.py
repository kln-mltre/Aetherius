"""The public version is a valid semver and mirrors the single source, version.py."""

from __future__ import annotations

import re

import pytest

import aetherius

pytestmark = pytest.mark.unit

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")


def test_version_is_semver() -> None:
    assert _SEMVER.match(aetherius.__version__), aetherius.__version__


def test_version_matches_source() -> None:
    from aetherius.version import __version__ as source_version

    assert aetherius.__version__ == source_version
