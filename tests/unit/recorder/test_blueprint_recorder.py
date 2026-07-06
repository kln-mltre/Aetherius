"""Unit tests for recorder/blueprint_recorder.py: the pure event->Blueprint transformation.

Everything here runs without a browser. ``record_blueprint`` is exercised end-to-end by faking the
:class:`RecordingSession` so the assembly and canonical validation are covered in the base suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.core.blueprint.loader import load_blueprint
from aetherius.core.blueprint.validator import validate_for_act
from aetherius.recorder import blueprint_recorder as br
from aetherius.recorder.blueprint_recorder import (
    assemble_blueprint,
    events_to_steps,
    record_blueprint,
)
from aetherius.recorder.capture import RecordedEvent
from aetherius.recorder.selector_synth import Candidate, ElementDescriptor

pytestmark = pytest.mark.unit


def _field(selector: str, **kwargs: object) -> ElementDescriptor:
    return ElementDescriptor(
        tag="input",
        css_path="form > input",
        candidates=(Candidate("id", selector, "css", True),),
        **kwargs,  # type: ignore[arg-type]
    )


def test_password_becomes_a_secret_and_its_value_is_never_present() -> None:
    events = [
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#password", name="password")),
    ]
    steps, secrets = events_to_steps(events)
    assert secrets == ["password"]
    assert steps == [{"action": "fill", "selector": "#password", "value": "{{ secrets.password }}"}]


def test_username_like_field_becomes_a_secret_when_credentials_are_on() -> None:
    events = [
        RecordedEvent(kind="fill", value="alice", descriptor=_field("#user", name="username")),
    ]
    steps, secrets = events_to_steps(events, credentials_as_secrets=True)
    assert secrets == ["username"]
    assert steps[0]["value"] == "{{ secrets.username }}"


def test_credentials_off_keeps_username_literal_but_password_stays_secret() -> None:
    events = [
        RecordedEvent(kind="fill", value="alice", descriptor=_field("#user", name="username")),
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#pw", name="password")),
    ]
    steps, secrets = events_to_steps(events, credentials_as_secrets=False)
    assert steps[0]["value"] == "alice"
    assert secrets == ["password"]  # a password is always a secret, its value never captured


def test_consecutive_fills_on_the_same_field_coalesce_to_the_last_value() -> None:
    events = [
        RecordedEvent(kind="fill", value="a", descriptor=_field("#q", name="q")),
        RecordedEvent(kind="fill", value="ab", descriptor=_field("#q", name="q")),
        RecordedEvent(kind="fill", value="abc", descriptor=_field("#q", name="q")),
    ]
    steps, _ = events_to_steps(events)
    assert steps == [{"action": "fill", "selector": "#q", "value": "abc"}]


def test_navigation_following_a_click_is_dropped_but_the_first_is_kept() -> None:
    events = [
        RecordedEvent(kind="navigate", url="https://site/login"),
        RecordedEvent(kind="click", descriptor=_field("#submit")),
        RecordedEvent(kind="navigate", url="https://site/dashboard"),  # caused by the click
    ]
    steps, _ = events_to_steps(events)
    actions = [s["action"] for s in steps]
    assert actions == ["navigate", "click"]
    assert steps[0]["url"] == "https://site/login"


def test_manual_navigation_not_preceded_by_a_click_is_kept() -> None:
    events = [
        RecordedEvent(kind="navigate", url="https://site/a"),
        RecordedEvent(kind="navigate", url="https://site/b"),  # typed in the address bar
    ]
    steps, _ = events_to_steps(events)
    assert [s["url"] for s in steps] == ["https://site/a", "https://site/b"]


def test_select_and_press_map_to_their_actions() -> None:
    events = [
        RecordedEvent(kind="select", value="FR", descriptor=_field("#country", name="country")),
        RecordedEvent(kind="press", key="Enter", descriptor=_field("#country", name="country")),
    ]
    steps, _ = events_to_steps(events)
    assert steps[0] == {"action": "select", "selector": "#country", "value": "FR"}
    assert steps[1] == {"action": "press", "key": "Enter", "selector": "#country"}


def test_text_selector_type_is_emitted_but_css_default_is_omitted() -> None:
    text_target = ElementDescriptor(
        tag="button", css_path="b", candidates=(Candidate("text", "Log in", "text", True),)
    )
    css_target = ElementDescriptor(
        tag="button", css_path="b", candidates=(Candidate("id", "#go", "css", True),)
    )
    steps, _ = events_to_steps(
        [
            RecordedEvent(kind="click", descriptor=text_target),
            RecordedEvent(kind="click", descriptor=css_target),
        ]
    )
    assert steps[0] == {"action": "click", "selector": "Log in", "selector_type": "text"}
    assert steps[1] == {"action": "click", "selector": "#go"}  # css default omitted


def test_two_anonymous_secret_fields_get_distinct_names() -> None:
    events = [
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#a")),
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#b")),
    ]
    _, secrets = events_to_steps(events)
    assert secrets == ["secret", "secret_2"]


def test_assemble_blueprint_is_minimal_and_ordered() -> None:
    bp = assemble_blueprint("quotes.login", [{"action": "navigate", "url": "u"}], ["password"])
    assert list(bp.keys()) == ["aetherius", "name", "act", "secrets", "steps"]
    assert bp["act"] == "continuum"
    assert bp["secrets"] == ["password"]

    no_secrets = assemble_blueprint("x", [{"action": "navigate", "url": "u"}], [])
    assert "secrets" not in no_secrets  # omitted when empty


def test_record_blueprint_writes_a_schema_valid_file(monkeypatch, tmp_path: Path) -> None:
    canned = [
        RecordedEvent(kind="navigate", url="https://quotes.toscrape.com/login"),
        RecordedEvent(kind="fill", value="alice", descriptor=_field("#username", name="username")),
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#password", name="password")),
        RecordedEvent(kind="click", descriptor=_field("#submit")),
    ]

    class _FakeSession:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def record(self) -> list[RecordedEvent]:
            return canned

    monkeypatch.setattr(br, "RecordingSession", _FakeSession)

    path = record_blueprint("quotes.login", "https://quotes.toscrape.com/login", out_dir=tmp_path)
    assert path == tmp_path / "quotes.login.blueprint.json"

    loaded = load_blueprint(path)
    validate_for_act(loaded)  # canonical validation: must not raise
    assert loaded.act == "continuum"
    assert set(loaded.secrets) == {"username", "password"}
    assert [s.action for s in loaded.steps] == ["navigate", "fill", "fill", "click"]

    raw = json.loads(path.read_text())
    pw_step = next(s for s in raw["steps"] if s.get("selector") == "#password")
    assert pw_step["value"] == "{{ secrets.password }}"
