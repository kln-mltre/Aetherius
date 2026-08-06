"""Tests for core/extraction/json_extractor.py"""

from __future__ import annotations

import json

import pytest

from aetherius.core.errors import ExtractionError
from aetherius.core.extraction.json_extractor import ExtractSpec, extract_json

pytestmark = pytest.mark.unit

_EVENTS = [
    {
        "id": "1",
        "start": "2026-09-07T08:00",
        "eventCategory": "Cours",
        "backgroundColor": "#3b82f6",
    },
    {
        "id": "2",
        "start": "2026-09-07T10:00",
        "eventCategory": "Vacances",
        "backgroundColor": "#f00",
    },
    {"id": "3", "start": "2026-09-07T14:00", "eventCategory": "TD", "backgroundColor": "#10b981"},
]

_BODY = json.dumps(_EVENTS).encode()


def test_extract_all_items() -> None:
    spec = {"items": ExtractSpec(from_="json", path="$[*]")}
    result = extract_json(_BODY, spec)
    assert len(result["items"]) == 3


def test_where_filter() -> None:
    spec = {
        "events": ExtractSpec(
            from_="json",
            path="$[*]",
            where="item.eventCategory != 'Vacances'",
        )
    }
    result = extract_json(_BODY, spec)
    assert len(result["events"]) == 2
    categories = [e["eventCategory"] for e in result["events"]]
    assert "Vacances" not in categories


def test_fields_mapping() -> None:
    spec = {
        "events": ExtractSpec(
            from_="json",
            path="$[*]",
            where="item.eventCategory != 'Vacances'",
            fields={"id": "$.id", "category": "$.eventCategory"},
        )
    }
    result = extract_json(_BODY, spec)
    assert result["events"] == [
        {"id": "1", "category": "Cours"},
        {"id": "3", "category": "TD"},
    ]


def test_invalid_json_raises() -> None:
    with pytest.raises(ExtractionError, match="Cannot parse JSON"):
        extract_json(b"not json", {"x": ExtractSpec(from_="json", path="$")})


def test_disallowed_where_node_raises() -> None:
    spec = {
        "x": ExtractSpec(
            from_="json",
            path="$[*]",
            where="__import__('os').system('rm -rf /')",
        )
    }
    with pytest.raises(ExtractionError, match="Disallowed"):
        extract_json(_BODY, spec)


def test_where_dunder_attribute_is_blocked() -> None:
    # ast.Attribute is allowlisted, so dunder traversal (the doorway to __globals__/__subclasses__)
    # must be rejected explicitly, even without a call.
    spec = {"x": ExtractSpec(from_="json", path="$[*]", where="item.__class__ != 0")}
    with pytest.raises(ExtractionError, match="Disallowed"):
        extract_json(_BODY, spec)


def test_where_dunder_oracle_is_blocked() -> None:
    # A comparison alone (no Call/Subscript) is enough to probe live objects; it must not evaluate.
    spec = {
        "x": ExtractSpec(
            from_="json",
            path="$[*]",
            where="'os' in item.__class__.__init__.__globals__",
        )
    }
    with pytest.raises(ExtractionError, match="Disallowed"):
        extract_json(_BODY, spec)


def test_where_single_underscore_field_is_allowed() -> None:
    # Only dunders are dangerous; a legitimate JSON key with a single leading underscore stays usable.
    body = json.dumps([{"_private": 1}, {"_private": 2}]).encode()
    spec = {"rows": ExtractSpec(from_="json", path="$[*]", where="item._private > 1")}
    result = extract_json(body, spec)
    assert result["rows"] == [{"_private": 2}]


def test_where_reaches_a_nested_field() -> None:
    # Real payloads nest their discriminators (Croustillant: `type.code`). The embedded engine reads
    # a plain object graph, so it has always answered this; only the top level was wrapped here,
    # which made the same predicate raise on one engine and filter on the other.
    body = json.dumps(
        [
            {"nom": "Resto U", "type": {"code": 1, "libelle": "Restaurant"}},
            {"nom": "Agree", "type": {"code": 4, "libelle": "Restaurant agree"}},
        ]
    ).encode()
    spec = {"rows": ExtractSpec(from_="json", path="$[*]", where="item.type.code != 4")}
    result = extract_json(body, spec)
    assert [row["nom"] for row in result["rows"]] == ["Resto U"]


@pytest.mark.parametrize("spelling", ["true", "True"])
def test_where_accepts_both_spellings_of_a_boolean_literal(spelling: str) -> None:
    # Jinja and the embedded engine's single evaluator spell literals in lower case; here `where`
    # is raw Python, where `true` is an undefined name. Both spellings must mean the same thing, or
    # the natural one raises on this engine and filters on the other.
    body = json.dumps([{"id": 1, "is_active": True}, {"id": 2, "is_active": False}]).encode()
    spec = {"rows": ExtractSpec(from_="json", path="$[*]", where=f"item.is_active == {spelling}")}
    assert extract_json(body, spec)["rows"] == [{"id": 1, "is_active": True}]


def test_where_accepts_the_lower_case_none_literal() -> None:
    body = json.dumps([{"id": 1, "zone": None}, {"id": 2, "zone": "Talence"}]).encode()
    spec = {"rows": ExtractSpec(from_="json", path="$[*]", where="item.zone != none")}
    assert extract_json(body, spec)["rows"] == [{"id": 2, "zone": "Talence"}]


def test_where_on_an_absent_nested_field_raises() -> None:
    # An absent field is an error on both engines, not a silent filter: a typo in a Blueprint must
    # not read as "nothing matched".
    body = json.dumps([{"type": {"code": 1}}]).encode()
    spec = {"rows": ExtractSpec(from_="json", path="$[*]", where="item.type.absent != 4")}
    with pytest.raises(ExtractionError, match="Error evaluating where expression"):
        extract_json(body, spec)


def test_where_with_boolean_logic() -> None:
    spec = {
        "events": ExtractSpec(
            from_="json",
            path="$[*]",
            where="item.eventCategory != 'Vacances' and item.eventCategory != 'TD'",
        )
    }
    result = extract_json(_BODY, spec)
    assert len(result["events"]) == 1
    assert result["events"][0]["eventCategory"] == "Cours"
