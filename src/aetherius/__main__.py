"""Enable ``python -m aetherius`` as an alias for the ``aetherius`` console script.

Used by the Console and the TypeScript SDK to spawn the daemon with the current interpreter, without
depending on the ``aetherius`` entry point being on PATH.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
