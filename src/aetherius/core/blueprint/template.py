"""Runtime interpolation of the {{ }} syntax over inputs, secrets, vars, env, and step outputs.

Uses Jinja2 SandboxedEnvironment with StrictUndefined so missing variables surface
immediately as TemplateError rather than silently rendering to empty strings.

When a value is a "bare" single-expression string like ``{{ steps.req.events }}``, the raw
Python object is returned instead of its string representation — this preserves lists and dicts
through the outputs rendering pipeline.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from jinja2 import StrictUndefined, Undefined as _Undefined
from jinja2.sandbox import SandboxedEnvironment

from ..errors import TemplateError

# Matches strings that are exactly one {{ … }} expression (possibly with surrounding whitespace).
# The body may not contain "}}": a lazy ".*?" backtracks past the first closer, so
# "{{ vars.api }}/{{ inputs.id }}" — the most ordinary way to build a URL — looked like one
# expression whose source was "vars.api }}/{{ inputs.id", and failed to parse instead of rendering.
_BARE_EXPR = re.compile(r"^\s*\{\{((?:(?!\}\}).)*)\}\}\s*$", re.DOTALL)

# ── Custom filters ─────────────────────────────────────────────────────────────


def _filter_add_days(value: str, n: int) -> str:
    """Add *n* days to an ISO 8601 date string and return an ISO 8601 date string."""
    try:
        date = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise TemplateError(f"add_days: cannot parse date {value!r}") from exc
    return (date + datetime.timedelta(days=n)).isoformat()


def _filter_sub_days(value: str, n: int) -> str:
    return _filter_add_days(value, -n)


def _filter_format_date(value: str, fmt: str) -> str:
    """Reformat an ISO 8601 date string using a strftime format string."""
    try:
        date = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise TemplateError(f"format_date: cannot parse date {value!r}") from exc
    return date.strftime(fmt)


# ── Jinja2 environment ────────────────────────────────────────────────────────


def _make_env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(undefined=StrictUndefined)
    env.filters["add_days"] = _filter_add_days
    env.filters["sub_days"] = _filter_sub_days
    env.filters["format_date"] = _filter_format_date
    return env


_env = _make_env()

# ── Public API ────────────────────────────────────────────────────────────────


def render_value(value: Any, ctx: dict[str, Any]) -> Any:
    """Recursively render {{ }} expressions in *value* against *ctx*.

    Strings are rendered through Jinja2. Dicts and lists are rendered recursively.
    Non-string scalars (int, bool, None, …) are passed through unchanged.

    When a string is a single bare ``{{ expr }}`` expression, the raw Python object is
    returned (not its string representation), so lists and dicts survive the pipeline.

    Raises:
        TemplateError: on undefined variable, bad filter, or syntax error.
    """
    if isinstance(value, str):
        m = _BARE_EXPR.match(value)
        if m:
            # Single-expression: evaluate and return the raw Python value.
            try:
                # undefined_to_none=False so we receive Undefined rather than None.
                compiled = _env.compile_expression(m.group(1).strip(), undefined_to_none=False)
                result = compiled(**ctx)
                # compile_expression ignores StrictUndefined; raise explicitly.
                if isinstance(result, _Undefined):
                    raise TemplateError(f"Undefined variable in expression: {m.group(1).strip()!r}")
                return result
            except TemplateError:
                # A filter already raised the typed error; keep its message rather than nest it.
                raise
            except Exception as exc:
                # Not only jinja2's own errors: a filter applied to the wrong type raises a plain
                # TypeError from the standard library, which would otherwise escape untyped and be
                # reported as a crash instead of a Blueprint mistake.
                raise TemplateError(f"Template expression failed: {exc}") from exc
        # Multi-part string: render as text.
        try:
            return _env.from_string(value).render(ctx)
        except TemplateError:
            raise
        except Exception as exc:
            raise TemplateError(f"Template rendering failed: {exc}") from exc
    if isinstance(value, dict):
        return {k: render_value(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(item, ctx) for item in value]
    return value
