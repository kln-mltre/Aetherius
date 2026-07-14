"""Helpers shared by the CLI command groups."""

from __future__ import annotations

import typer


def parse_pairs(pairs: list[str], *, label: str) -> dict[str, str]:
    """Parse a list of ``key=value`` CLI options into a dict.

    Raises:
        typer.BadParameter: an entry has no ``=``.
    """
    result: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"Malformed {label} {pair!r}: expected key=value.")
        key, _, value = pair.partition("=")
        result[key] = value
    return result
