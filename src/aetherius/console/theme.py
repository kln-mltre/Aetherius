"""Consistent visual theme for the Console (palette, wordmark and ornaments).

Pure data and tiny ornament factories: a registered Textual Theme, the per-Act accent colors,
and the decorative pixel ornaments (mosaic frieze, wordmark, cloud bank, starfield) shared by
the screens. No widget logic here.

Art direction: nocturnal aether — the temple at night. Dark void sky, moonlit clouds, imperial
gold relics, tyrian violet for the veiled and the mystic, laurel green for triumph. Pixel-mosaic
friezes and starfields as details. Echoes the Latin name of the tool.
"""

from __future__ import annotations

from rich.text import Text

from textual.theme import Theme

# Palette: single source for the Theme, the Act badges and every decorative detail.
# Dominants requested by the user: pourpre, violet, dark green — readability kept by leaving
# body text near-white and letting the purples carry structure (frames, friezes), not prose.
VOID = "#141020"  # violet-tinted night background
NIMBUS = "#1c1730"  # twilight surface
PANEL = "#282045"  # raised panels
MOONLIGHT = "#dcd7e8"  # violet-tinged moonlight, main text
STONE = "#7f7a90"  # weathered stone, muted and pending things
VIOLET = "#9d7bd8"  # twilight violet, primary structure
TYRIAN = "#b0568c"  # tyrian pourpre, the imperial dye, mystic accents
GOLD = "#d4af37"  # imperial gold, reserved for stars and the wordmark
LAUREL = "#4e8a5a"  # dark laurel green, success and vines
AMBER = "#d08a3e"  # torchlight, warnings
POMPEIAN = "#c1564a"  # pompeian red, errors

AETHERIUS_THEME = Theme(
    name="aetherius",
    primary=VIOLET,
    secondary=TYRIAN,
    accent=GOLD,
    warning=AMBER,
    error=POMPEIAN,
    success=LAUREL,
    foreground=MOONLIGHT,
    background=VOID,
    surface=NIMBUS,
    panel=PANEL,
    dark=True,
)

# Accent color per Act, used for badges across screens. Vector is the only implemented Act
# today (core.runtime.engine.IMPLEMENTED_ACTS); the other three share the muted stone tone.
PER_ACT_COLOR: dict[str, str] = {
    "vector": LAUREL,
    "continuum": STONE,
    "oracle": STONE,
    "phantom": STONE,
}

ACT_LABELS: dict[str, str] = {
    "vector": "I - Vector",
    "continuum": "II - Continuum",
    "oracle": "III - Oracle",
    "phantom": "IV - Phantom",
}

# Ornaments. The wordmark spells AETHERIVS (Roman V), generated once with pyfiglet
# (font "ansi_shadow", dev-time only — never a runtime dependency) and frozen here.
# All rows are 69 columns, guarded by a test. Regenerate with:
#   python -c "import pyfiglet; print(pyfiglet.figlet_format('AETHERIVS', font='ansi_shadow'))"
WORDMARK: tuple[str, ...] = (
    " █████╗ ███████╗████████╗██╗  ██╗███████╗██████╗ ██╗██╗   ██╗███████╗",
    "██╔══██╗██╔════╝╚══██╔══╝██║  ██║██╔════╝██╔══██╗██║██║   ██║██╔════╝",
    "███████║█████╗     ██║   ███████║█████╗  ██████╔╝██║██║   ██║███████╗",
    "██╔══██║██╔══╝     ██║   ██╔══██║██╔══╝  ██╔══██╗██║╚██╗ ██╔╝╚════██║",
    "██║  ██║███████╗   ██║   ██║  ██║███████╗██║  ██║██║ ╚████╔╝ ███████║",
    "╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝",
)
MOTTO = "per nubes, ad aethera"
STARFIELD = "˚ ✦ ·       ✦      · ˚       ✦ ·      ˚ ·     ✦    · ˚ ✦      · ✦ ˚"

# The hedera (Latin for ivy) is the leaf ornament Romans carved into inscriptions as a
# separator. It is the closest thing to a vine a character grid can honestly offer.
HEDERA = "❦"
HEDERA_ALT = "❧"


def frieze(width: int = 69) -> str:
    """Horizontal mosaic frieze strip, the Console's recurring pixel ornament."""
    return ("▚▞" * ((width + 1) // 2))[:width]


def frieze_column(height: int) -> str:
    """Vertical mosaic frieze (one glyph per line), for flanking content like temple columns."""
    return "\n".join("▚" if i % 2 == 0 else "▞" for i in range(height))


def garland(width: int = 45) -> str:
    """Ivy garland: hederae threaded on a vine line, the Console's vine ornament."""
    inner = "─" * max((width - 5) // 2, 1)
    return f"{HEDERA_ALT}{inner} {HEDERA} {inner}{HEDERA_ALT}"


def starred(title: str) -> Text:
    """Title flanked by small gold stars — the recurring ornament for screen titles."""
    text = Text()
    text.append("✦ ", style=GOLD)
    text.append(title)
    text.append(" ✦", style=GOLD)
    return text
