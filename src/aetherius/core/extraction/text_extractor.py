"""Text extraction: the decoded response body, verbatim.

The third dialect of ``extract``, and the simplest: no path, no selector, no filtering. A response
that is neither JSON nor HTML — iCalendar, CSV, ``text/plain`` — is data too, and interpreting it is
the application's job (docs/phase-3/3-i-extraction-texte.md).

Decoding follows the response's ``Content-Type``, and that is the one place where the two engines
could diverge in silence: the embedded engine has no ``TextDecoder`` to lean on (absent from React
Native, ICU-complete under Node — using it would make the CI and the device disagree). So both
engines carry the **same bounded table** rather than one delegating to its platform:

    iso-8859-1 / latin-1 …  ->  strict Latin-1 (the Python codec, *not* the WHATWG alias to cp1252)
    windows-1252 / cp1252   ->  cp1252
    anything else, or none  ->  UTF-8

Falling back to UTF-8 for an unknown label is what httpx does too. Widening the table is a decision
to take on both sides at once; taking every codec Python knows would be the silent divergence this
milestone exists to avoid. Invalid bytes are always **replaced**, never raised: the engine is not the
one who can tell that the caller aimed at the wrong source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Aliases are matched after lowercasing and stripping quotes/whitespace. Kept small on purpose: the
# twin table lives in sdks/engine/src/extraction/charset.ts and the two are compared by a
# conformance case.
_CODECS: dict[str, str] = {
    "iso-8859-1": "iso-8859-1",
    "iso8859-1": "iso-8859-1",
    "iso_8859-1": "iso-8859-1",
    "latin-1": "iso-8859-1",
    "latin1": "iso-8859-1",
    "l1": "iso-8859-1",
    "windows-1252": "cp1252",
    "cp1252": "cp1252",
    "win-1252": "cp1252",
}

_DEFAULT_CODEC = "utf-8"


@dataclass
class TextExtractSpec:
    from_: str  # "text"


def resolve_charset(content_type: str | None) -> str:
    """The codec to decode a body served with *content_type*, UTF-8 when it says nothing usable."""
    if not content_type:
        return _DEFAULT_CODEC

    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() != "charset":
            continue
        label = value.strip().strip('"').strip("'").lower()
        return _CODECS.get(label, _DEFAULT_CODEC)
    return _DEFAULT_CODEC


def decode_body(body: bytes, content_type: str | None) -> str:
    """Decode *body* per its declared charset. A BOM is kept — the Python codec keeps it too."""
    return body.decode(resolve_charset(content_type), errors="replace")


def extract_text(
    body: bytes,
    spec: dict[str, "TextExtractSpec"],
    content_type: str | None = None,
) -> dict[str, Any]:
    """Give every named spec in *spec* the whole decoded body.

    An empty body yields an empty string, not ``None``: a response with nothing in it is a result.
    """
    if not spec:
        return {}
    text = decode_body(body, content_type)
    return {output_name: text for output_name in spec}
