"""Blueprint discovery and validation for the Library screen.

Pure functions, deliberately free of Textual imports, so they're trivially unit-testable and
reusable (e.g. by a future `aetherius list` CLI command) without pulling in the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...core.blueprint.loader import load_blueprint
from ...core.blueprint.models import Blueprint
from ...core.blueprint.validator import validate_for_act
from ...core.errors import BlueprintError

_BLUEPRINT_GLOBS = ("*.blueprint.json", "*.blueprint.yaml", "*.blueprint.yml")


@dataclass(frozen=True)
class BlueprintEntry:
    path: Path
    blueprint: Blueprint | None
    act: str | None
    error: str | None


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
    """Load and validate every Blueprint file found in *dirs*, newest-name-first is not
    guaranteed; invalid files are kept in the result with their error instead of raising."""
    entries: list[BlueprintEntry] = []
    seen: set[Path] = set()

    for directory in dirs:
        for pattern in _BLUEPRINT_GLOBS:
            for path in sorted(directory.glob(pattern)):
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
