"""Build the three extraction dialects from a step's raw ``extract`` block and run them.

Lifted out of ``VectorDriver`` so the mapping "raw spec -> typed spec" has one home: the driver
consumes it, and the conformance corpus exercises the real path rather than a copy of it. The
embedded engine mirrors this module in ``sdks/engine/src/extraction/index.ts``; defaults living in
two places would be the quiet way for the two engines to drift.

The body arrives as **bytes**, with the response's ``Content-Type`` beside it rather than the
response object itself: only the text dialect needs the encoding label, and handing the whole
response down here would tie extraction to httpx (and to nothing at all on the other engine). JSON
and HTML keep decoding as UTF-8 with replacement, exactly as before — the text dialect is the one
that follows the header (see ``text_extractor``).

Note: extraction specs are *not* rendered through the template engine — a selector or a JSONPath is
taken verbatim. That has always been the behaviour; it is stated here because the absence of a
renderer in the signature is otherwise easy to read as an oversight.
"""

from __future__ import annotations

from typing import Any

from .html_extractor import HtmlExtractSpec, extract_html
from .json_extractor import ExtractSpec, extract_json
from .text_extractor import TextExtractSpec, extract_text


def dispatch_extract(
    body: bytes,
    raw_specs: dict[str, Any],
    *,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Run every named extraction in *raw_specs* against *body* and collect the results."""
    json_specs: dict[str, ExtractSpec] = {}
    html_specs: dict[str, HtmlExtractSpec] = {}
    text_specs: dict[str, TextExtractSpec] = {}

    for name, raw in raw_specs.items():
        from_val: str = raw.get("from", "json")
        if from_val == "json":
            json_specs[name] = ExtractSpec(
                from_=from_val,
                path=raw.get("path", "$"),
                where=raw.get("where"),
                fields={k: v for k, v in (raw.get("fields") or {}).items()},
            )
        elif from_val == "text":
            text_specs[name] = TextExtractSpec(from_=from_val)
        else:
            # Anything unknown stays HTML, as it always has: tightening that here would reject
            # Blueprints that run today, for a typo the validator is better placed to catch.
            html_specs[name] = HtmlExtractSpec(
                from_=from_val,
                selector=raw.get("selector", ""),
                selector_type=raw.get("selector_type", "css"),
                attr=raw.get("attr"),
                multiple=raw.get("multiple", True),
            )

    result: dict[str, Any] = {}
    if json_specs:
        result.update(extract_json(body, json_specs))
    if html_specs:
        result.update(extract_html(body, html_specs))
    if text_specs:
        result.update(extract_text(body, text_specs, content_type))
    return result
