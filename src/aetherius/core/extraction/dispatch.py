"""Build the two extraction dialects from a step's raw ``extract`` block and run them.

Lifted out of ``VectorDriver`` so the mapping "raw spec -> typed spec" has one home: the driver
consumes it, and the conformance corpus exercises the real path rather than a copy of it. The
embedded engine mirrors this module in ``sdks/engine/src/extraction/index.ts``; defaults living in
two places would be the quiet way for the two engines to drift.

Note: extraction specs are *not* rendered through the template engine — a selector or a JSONPath is
taken verbatim. That has always been the behaviour; it is stated here because the absence of a
renderer in the signature is otherwise easy to read as an oversight.
"""

from __future__ import annotations

from typing import Any

from .html_extractor import HtmlExtractSpec, extract_html
from .json_extractor import ExtractSpec, extract_json


def dispatch_extract(body: bytes, raw_specs: dict[str, Any]) -> dict[str, Any]:
    """Run every named extraction in *raw_specs* against *body* and collect the results."""
    json_specs: dict[str, ExtractSpec] = {}
    html_specs: dict[str, HtmlExtractSpec] = {}

    for name, raw in raw_specs.items():
        from_val: str = raw.get("from", "json")
        if from_val == "json":
            json_specs[name] = ExtractSpec(
                from_=from_val,
                path=raw.get("path", "$"),
                where=raw.get("where"),
                fields={k: v for k, v in (raw.get("fields") or {}).items()},
            )
        else:
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
    return result
