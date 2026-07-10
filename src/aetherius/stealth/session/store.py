"""Persistent browser profiles and per-run artifact directories.

A *profile* is a directory Playwright reuses across runs to carry authentic cookies, cache and
history (``launch_persistent_context``). A *run directory* collects the artifacts a single run
produces (screenshots, HAR, DOM snapshots). Both live under the configured ``data_dir``.

Only directory resolution lives here for now. Warmup (building an authentic history before an
automation) and storage-state export are later milestones and are intentionally left out.
"""

from __future__ import annotations

from pathlib import Path

from ...config.settings import get_settings


def resolve_profile_dir(profile: str | None) -> Path | None:
    """Return the directory for a persistent browser *profile*, creating it on demand.

    Returns ``None`` when *profile* is falsy, signalling the caller to use an ephemeral
    (non-persistent) browser context instead.
    """
    if not profile:
        return None
    path = get_settings().profiles_dir / profile
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir(run_id: str) -> Path:
    """Return the artifact directory for *run_id*, creating it on demand."""
    path = get_settings().runs_dir / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path
