"""Tiny naming helpers shared by the recorder transforms: sanitize and de-duplicate identifiers."""

from __future__ import annotations

import re


def ident(raw: str | None, *, fallback: str) -> str:
    """Sanitize a free string into a lowercase identifier, or *fallback* if it is empty."""
    base = re.sub(r"[^a-z0-9_]+", "_", (raw or "").lower()).strip("_")
    return base or fallback


def unique(base: str, taken: set[str]) -> str:
    """Return *base*, suffixed (_2, _3, …) until it is not already in *taken*."""
    name, counter = base, 2
    while name in taken:
        name = f"{base}_{counter}"
        counter += 1
    return name
