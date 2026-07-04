"""JSON extraction via JSONPath, with optional per-item field mapping and a safe where predicate."""

from __future__ import annotations

import ast
import json
import types
from dataclasses import dataclass, field
from typing import Any

from jsonpath_ng.ext import parse as jpath_parse

from ..errors import ExtractionError

# AST node types allowed in a `where` expression.
# Anything outside this set (calls, imports, comprehensions, …) is rejected.
_ALLOWED_NODES = (
    ast.Expression,
    ast.Compare,
    ast.Name,
    ast.Attribute,
    ast.Constant,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Load,
)


@dataclass
class ExtractSpec:
    from_: str  # "json" | "html"
    path: str  # JSONPath expression, e.g. "$[*]"
    where: str | None = None  # per-item predicate, e.g. "item.eventCategory != 'Vacances'"
    fields: dict[str, str] = field(default_factory=dict)  # name -> JSONPath relative to item


def _eval_predicate(expr: str, item: Any) -> bool:
    """Evaluate a simple comparison expression against *item* with an AST safety check.

    *item* is wrapped in SimpleNamespace so `item.attr` dot-access works on JSON dicts.
    Raises ExtractionError if the expression contains disallowed AST nodes.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExtractionError(f"Invalid where expression {expr!r}: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExtractionError(
                f"Disallowed construct {type(node).__name__!r} in where expression {expr!r}. "
                "Only comparisons and boolean logic are permitted."
            )

    ns: Any
    if isinstance(item, dict):
        ns = types.SimpleNamespace(**item)
    else:
        ns = item

    try:
        return bool(eval(compile(tree, "<where>", "eval"), {"__builtins__": {}}, {"item": ns}))
    except Exception as exc:
        raise ExtractionError(f"Error evaluating where expression {expr!r}: {exc}") from exc


def _extract_fields(item_dict: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    """Extract sub-fields from a single matched item using relative JSONPath expressions."""
    result: dict[str, Any] = {}
    for field_name, path in fields.items():
        matches = jpath_parse(path).find(item_dict)
        if not matches:
            result[field_name] = None
        elif len(matches) == 1:
            result[field_name] = matches[0].value
        else:
            result[field_name] = [m.value for m in matches]
    return result


def extract_json(body: bytes, spec: dict[str, "ExtractSpec"]) -> dict[str, Any]:
    """Run all extraction specs in *spec* against a JSON *body* and return the collected data.

    Each key in *spec* becomes a key in the returned dict whose value is a list of matched items
    (or a single value when only one item matches and no fields mapping is defined).
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Cannot parse JSON response body: {exc}") from exc

    result: dict[str, Any] = {}

    for output_name, s in spec.items():
        try:
            matches = jpath_parse(s.path).find(data)
        except Exception as exc:
            raise ExtractionError(f"Invalid JSONPath {s.path!r}: {exc}") from exc

        items = [m.value for m in matches]

        if s.where:
            items = [item for item in items if _eval_predicate(s.where, item)]

        if s.fields:
            items = [
                _extract_fields(item if isinstance(item, dict) else {}, s.fields) for item in items
            ]

        result[output_name] = items

    return result
