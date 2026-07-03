"""Consistent visual theme for the Console (palette and styles).

Pure data: a registered Textual Theme plus a per-Act accent color, both consumed by every
screen that renders an Act badge (Home, Library, Catalog). No layout or widget logic here.
"""

from __future__ import annotations

from textual.theme import Theme

AETHERIUS_THEME = Theme(
    name="aetherius",
    primary="#7c9cff",
    secondary="#5ad1c8",
    accent="#f2b950",
    warning="#f2b950",
    error="#e5534b",
    success="#3fb950",
    foreground="#e6e6e6",
    background="#0d1117",
    surface="#151b23",
    panel="#1c2430",
    dark=True,
)

# Accent color per Act, used for badges across screens. Vector is the only implemented Act
# today (core.runtime.engine.IMPLEMENTED_ACTS); the other three share a muted "pending" tone.
PER_ACT_COLOR: dict[str, str] = {
    "vector": "#3fb950",
    "continuum": "#6e7681",
    "oracle": "#6e7681",
    "phantom": "#6e7681",
}

ACT_LABELS: dict[str, str] = {
    "vector": "I - Vector",
    "continuum": "II - Continuum",
    "oracle": "III - Oracle",
    "phantom": "IV - Phantom",
}
