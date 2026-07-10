"""Tests for stealth/session/store.py — profile and run directory resolution."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator

import pytest

from aetherius.config import settings as settings_mod
from aetherius.stealth.session import store

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Point the settings singleton at a temp data dir and reset its cache around the test.
    monkeypatch.setenv("AETHERIUS_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()


def test_resolve_profile_dir_none_for_empty() -> None:
    assert store.resolve_profile_dir(None) is None
    assert store.resolve_profile_dir("") is None


def test_resolve_profile_dir_creates_named_dir() -> None:
    path = store.resolve_profile_dir("tiktok")
    assert path is not None
    assert path.exists()
    assert path.name == "tiktok"
    assert path.parent.name == "profiles"


def test_run_dir_creates_dir() -> None:
    path = store.run_dir("run-123")
    assert path.exists()
    assert path.name == "run-123"
    assert path.parent.name == "runs"
