"""Command-line entry point.

Running ``aetherius`` with no argument opens the interactive Console (the terminal control center).
Subcommands (``run``, ``serve``, ``record``, ``validate``) are the scriptable, non-interactive paths.

Kept dependency-light on purpose: heavy imports (Textual for the Console, FastAPI for the daemon)
happen inside the relevant command, not at module import time.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Dispatch the CLI. Placeholder wiring for the skeleton."""
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "console"

    raise NotImplementedError(
        f"CLI command '{command}' is not implemented yet. This is the architecture skeleton; "
        "the Console (Textual) and the daemon (FastAPI) are upcoming milestones."
    )


if __name__ == "__main__":
    raise SystemExit(main())
