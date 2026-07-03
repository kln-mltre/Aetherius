"""Shared fixtures for the Aetherius test suite.

Exposes the key repository paths (root, examples, contracts) so tests stay independent of their own
location on disk. Kept dependency-light: nothing here imports an Act engine or a heavy extra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return _REPO_ROOT


@pytest.fixture(scope="session")
def examples_dir(repo_root: Path) -> Path:
    """Directory holding the runnable Blueprint examples."""
    return repo_root / "examples"


@pytest.fixture(scope="session")
def contracts_dir(repo_root: Path) -> Path:
    """Directory holding the language-agnostic contracts (source of truth)."""
    return repo_root / "contracts"
