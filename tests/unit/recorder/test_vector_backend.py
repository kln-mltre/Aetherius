"""Unit tests for the Vector recorder backend transform (pure, no browser) and the backend registry."""

from __future__ import annotations

import json

import pytest

from aetherius.core.errors import RecorderError
from aetherius.recorder.base import get_recorder, recorder_acts
from aetherius.recorder.vector_backend import transform

pytestmark = pytest.mark.unit


def _event(request: dict, extract: dict) -> dict:
    return {"kind": "http_request", "request": request, "extract": extract}


def test_request_and_records_extract_become_a_step_with_outputs() -> None:
    events = [
        _event(
            {
                "method": "GET",
                "url": "https://api/users",
                "headers": {},
                "body": None,
                "status": 200,
            },
            {"name": "users", "path": "$[*]", "fields": {"name": "$.name"}},
        )
    ]
    result = transform(events)
    assert len(result.steps) == 1
    step = result.steps[0]
    assert step["id"] == "req"
    assert step["action"] == "http.request"
    assert step["method"] == "GET" and step["url"] == "https://api/users"
    assert step["expect"] == {"status": 200}
    assert step["extract"] == {
        "users": {"from": "json", "path": "$[*]", "fields": {"name": "$.name"}}
    }
    assert result.outputs == {"users": "{{ steps.req.users }}"}


def test_auth_header_becomes_a_secret_never_stored_literally() -> None:
    events = [
        _event(
            {
                "method": "GET",
                "url": "u",
                "headers": {"Authorization": "Bearer s3cr3t"},
                "status": 200,
            },
            {"name": "data", "path": "$"},
        )
    ]
    result = transform(events)
    assert result.secrets == ["authorization"]
    assert result.steps[0]["headers"] == {"Authorization": "{{ secrets.authorization }}"}
    assert "s3cr3t" not in json.dumps(result.steps)


def test_form_body_is_parsed_and_content_type_kept() -> None:
    events = [
        _event(
            {
                "method": "POST",
                "url": "u",
                "headers": {"Content-Type": "application/x-www-form-urlencoded", "Accept": "*/*"},
                "body": "a=1&b=hello%20world",
                "status": 200,
            },
            {"name": "data", "path": "$"},
        )
    ]
    step = transform(events).steps[0]
    assert step["form"] == {"a": "1", "b": "hello world"}
    assert step["headers"] == {
        "Content-Type": "application/x-www-form-urlencoded"
    }  # Accept dropped


def test_json_body_is_parsed() -> None:
    events = [
        _event(
            {"method": "POST", "url": "u", "body": '{"q": "x"}', "status": 200},
            {"name": "d", "path": "$"},
        )
    ]
    assert transform(events).steps[0]["json"] == {"q": "x"}


def test_picks_on_the_same_request_coalesce_into_one_step() -> None:
    request = {"method": "GET", "url": "u", "headers": {}, "body": None, "status": 200}
    events = [
        _event(request, {"name": "a", "path": "$.a"}),
        _event(request, {"name": "b", "path": "$.b"}),
    ]
    result = transform(events)
    assert len(result.steps) == 1
    assert set(result.steps[0]["extract"]) == {"a", "b"}
    assert result.outputs == {"a": "{{ steps.req.a }}", "b": "{{ steps.req.b }}"}


def test_registry_knows_the_working_acts_and_rejects_pending_ones() -> None:
    assert recorder_acts() == {"continuum", "vector"}
    assert get_recorder("vector").act == "vector"
    with pytest.raises(RecorderError):
        get_recorder("oracle")  # pending milestone
    with pytest.raises(RecorderError):
        get_recorder("nope")  # unknown act
