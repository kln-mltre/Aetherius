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
