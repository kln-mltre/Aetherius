"""Blueprint discovery and validation for the Library screen.

Pure functions, deliberately free of Textual imports, so they're trivially unit-testable and
reusable (e.g. by a future `aetherius list` CLI command) without pulling in the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ...core.blueprint.loader import load_blueprint
from ...core.blueprint.models import Blueprint
from ...core.blueprint.validator import validate_for_act
from ...core.errors import BlueprintError
from ...core.runtime.engine import IMPLEMENTED_ACTS

_BLUEPRINT_GLOBS = ("*.blueprint.json", "*.blueprint.yaml", "*.blueprint.yml")


@dataclass(frozen=True)
class BlueprintEntry:
    path: Path
    blueprint: Blueprint | None
    act: str | None
    error: str | None


class EntryStatus(str, Enum):
    """A Blueprint's real state in the Library: well-formed and runnable, or why not."""

    INVALID = "invalid"  # schema or capability error: unusable as-is
    READY = "ready"  # valid and its Act has a driver: runnable now
    ACT_PENDING = "act pending"  # valid but its Act is not implemented yet


def entry_status(entry: BlueprintEntry) -> EntryStatus:
    """Classify *entry* by validity and Act runnability (the single source is IMPLEMENTED_ACTS)."""
    if entry.error is not None or entry.act is None:
        return EntryStatus.INVALID
    if entry.act in IMPLEMENTED_ACTS:
        return EntryStatus.READY
    return EntryStatus.ACT_PENDING


def discover_blueprint_dirs(start: Path | None = None) -> list[Path]:
    """Directories scanned by the Library: a repo checkout's `examples/`, plus `./blueprints/`
    relative to the current working directory, whichever of the two actually exist."""
    dirs: list[Path] = []

    repo_examples = _find_repo_examples(Path(__file__).resolve())
    if repo_examples is not None:
        dirs.append(repo_examples)

    cwd_blueprints = (start or Path.cwd()) / "blueprints"
    if cwd_blueprints.is_dir() and cwd_blueprints not in dirs:
        dirs.append(cwd_blueprints)

    return dirs


def _find_repo_examples(start: Path) -> Path | None:
    """Walk up from this file looking for a sibling `examples/` directory (repo checkout only;
    absent from an installed, non-editable distribution)."""
    for parent in start.parents:
        candidate = parent / "examples"
        if candidate.is_dir():
            return candidate
    return None


def scan_blueprints(dirs: list[Path]) -> list[BlueprintEntry]:
    """Load and validate every Blueprint file found in *dirs*, recursively.

    The scan recurses so examples can be organised into per-Act subdirectories (examples/vector,
    examples/continuum, ...) and user libraries into any tree. Invalid files are kept in the result
    with their error instead of raising."""
    entries: list[BlueprintEntry] = []
    seen: set[Path] = set()

    for directory in dirs:
        for pattern in _BLUEPRINT_GLOBS:
            for path in sorted(directory.rglob(pattern)):
                if path in seen:
                    continue
                seen.add(path)
                entries.append(_load_entry(path))

    return entries


def _load_entry(path: Path) -> BlueprintEntry:
    try:
        blueprint = load_blueprint(path)
        validate_for_act(blueprint)
    except BlueprintError as exc:
        return BlueprintEntry(path=path, blueprint=None, act=None, error=str(exc))
    return BlueprintEntry(path=path, blueprint=blueprint, act=blueprint.act, error=None)
