"""Data actions: http.request, extract, assert, set, screenshot, evaluate.

Specs projected by the builder catalogue. Object/array parameters (headers, form, outputs, ...) are
edited as JSON: the schema leaves their shape open on purpose, and the placeholders show the
expected form.
"""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "http.request",
        "Send an HTTP request and optionally extract from the response (Act I).",
        params=(
            ParamSpec("method", "string", default="GET", help="HTTP method.", placeholder="POST"),
            ParamSpec(
                "url",
                "string",
                required=True,
                help="Request URL.",
                placeholder="{{ vars.domain }}/api",
            ),
            ParamSpec(
                "headers",
                "object",
                help="Request headers.",
                placeholder='{"Accept": "application/json"}',
            ),
            ParamSpec("params", "object", help="Query-string parameters."),
            ParamSpec(
                "form", "object", help="URL-encoded form body (mutually exclusive with json)."
            ),
            ParamSpec("json", "object", help="JSON body (mutually exclusive with form)."),
            ParamSpec(
                "expect", "object", help="Response assertions.", placeholder='{"status": 200}'
            ),
            ParamSpec(
                "extract",
                "object",
                help="Named extractions from the response: from='json' (JSONPath), "
                "from='html' (CSS/XPath) or from='text' (the decoded body).",
                placeholder='{"items": {"from": "json", "path": "$[*]"}}',
            ),
        ),
    ),
    ActionSpec(
        "extract",
        "Read values from the current page's DOM into named outputs (Act II).",
        params=(
            ParamSpec(
                "outputs",
                "object",
                required=True,
                help="Map of output name to a selector spec (as: text/number/html/attr/list, "
                "or each/fields for records).",
                placeholder='{"title": {"selector": "h1", "as": "text"}}',
            ),
        ),
    ),
    ActionSpec(
        "assert",
        "Fail the run unless a rendered condition is truthy.",
        params=(
            ParamSpec(
                "condition",
                "string",
                required=True,
                help="Expression that must be truthy.",
                placeholder="{{ steps.week.status_code == 200 }}",
            ),
            ParamSpec("message", "string", help="Message shown when the assertion fails."),
        ),
    ),
    ActionSpec(
        "set",
        "Store a rendered value under this step's id, for later interpolation.",
        params=(
            ParamSpec(
                "value",
                "string",
                required=True,
                help="Value to store.",
                placeholder="{{ inputs.group }}",
            ),
        ),
    ),
    ActionSpec(
        "screenshot",
        "Capture a screenshot artifact of the page or an element (Act II).",
        params=(
            ParamSpec(
                "name", "string", help="File name for the artifact (defaults to the step id)."
            ),
            ParamSpec("selector", "string", help="Element to capture; omit for the whole page."),
            ParamSpec(
                "full_page",
                "boolean",
                default=False,
                help="Capture the full scrollable page when no selector is given.",
            ),
            ParamSpec(
                "selector_type",
                "string",
                default="css",
                help="How to read 'selector': css (default), xpath or text.",
            ),
        ),
    ),
    ActionSpec(
        "evaluate",
        "Run injected JavaScript in the page and return its result (Act II).",
        params=(
            ParamSpec(
                "script",
                "string",
                required=True,
                help="JavaScript expression or function.",
                placeholder="() => document.title",
            ),
            ParamSpec("arg", "object", help="Optional argument passed to the script."),
        ),
    ),
)
