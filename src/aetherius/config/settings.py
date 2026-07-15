"""Environment-driven settings via pydantic-settings.

Central place for filesystem locations shared across runs: persistent browser profiles,
run artifacts (screenshots, HAR, DOM snapshots). Kept intentionally small; it grows as later
milestones (daemon, sessions warmup) need more knobs. Everything is overridable through the
``AETHERIUS_`` environment prefix so deployments never hardcode paths.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..network.pool import RotationStrategy


def _default_data_dir() -> Path:
    """Base directory for Aetherius state, resolved once from the home directory."""
    return Path.home() / ".aetherius"


class AetheriusSettings(BaseSettings):
    """Runtime configuration resolved from the environment (prefix ``AETHERIUS_``)."""

    model_config = SettingsConfigDict(env_prefix="AETHERIUS_", extra="ignore")

    data_dir: Path = Field(default_factory=_default_data_dir)

    # Network identity (Jalon G): a default proxy/pool routes any Blueprint without editing it.
    # ``AETHERIUS_PROXY_POOL`` takes a JSON list; a lone ``AETHERIUS_PROXY_URL`` is a pool of one.
    proxy_url: str | None = None
    proxy_pool: list[str] = Field(default_factory=list)
    proxy_rotate: RotationStrategy = "per_run"

    @property
    def profiles_dir(self) -> Path:
        """Where persistent browser profiles live (one subdirectory per named profile)."""
        return self.data_dir / "profiles"

    @property
    def runs_dir(self) -> Path:
        """Where per-run artifacts are written (one subdirectory per run id)."""
        return self.data_dir / "runs"

    @property
    def db_path(self) -> Path:
        """SQLite file backing durable state (schedules, run history, inter-run state).

        Introduced for the Phase 1.5 store (Jalon A); a single portable file so the daemon survives
        restarts. See docs/phase-1.5/a-store.md.
        """
        return self.data_dir / "aetherius.db"


@lru_cache(maxsize=1)
def get_settings() -> AetheriusSettings:
    """Return the process-wide settings singleton (cached; reads the environment once)."""
    return AetheriusSettings()
