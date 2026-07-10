"""Unit tests for the recorder transform and assembly (pure, no browser).

``events_to_steps`` returns ``(steps, secrets, inputs, outputs)``. ``record_blueprint`` is exercised
end-to-end by faking :class:`RecordingSession`, so assembly + canonical validation run in base CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.core.blueprint.loader import load_blueprint
from aetherius.core.blueprint.validator import validate_for_act
from aetherius.recorder import blueprint_recorder as br
from aetherius.recorder._transform import events_to_steps
from aetherius.recorder.base import RecordingResult
from aetherius.recorder.blueprint_recorder import assemble_blueprint, record_blueprint
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


# ── actions & credentials ────────────────────────────────────────────────────
def test_password_becomes_a_secret_and_its_value_is_never_present() -> None:
    events = [
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#password", name="password"))
    ]
    steps, secrets, _, _ = events_to_steps(events)
    assert secrets == ["password"]
    assert steps == [{"action": "fill", "selector": "#password", "value": "{{ secrets.password }}"}]


def test_username_like_field_becomes_a_secret_when_credentials_are_on() -> None:
    events = [
        RecordedEvent(kind="fill", value="alice", descriptor=_field("#user", name="username"))
    ]
    steps, secrets, _, _ = events_to_steps(events, credentials_as_secrets=True)
    assert secrets == ["username"]
    assert steps[0]["value"] == "{{ secrets.username }}"


def test_credentials_off_keeps_username_literal_but_password_stays_secret() -> None:
    events = [
        RecordedEvent(kind="fill", value="alice", descriptor=_field("#user", name="username")),
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#pw", name="password")),
    ]
    steps, secrets, _, _ = events_to_steps(events, credentials_as_secrets=False)
    assert steps[0]["value"] == "alice"
    assert secrets == ["password"]  # a password is always a secret, its value never captured


def test_consecutive_fills_on_the_same_field_coalesce_to_the_last_value() -> None:
    events = [
        RecordedEvent(kind="fill", value="a", descriptor=_field("#q", name="q")),
        RecordedEvent(kind="fill", value="ab", descriptor=_field("#q", name="q")),
        RecordedEvent(kind="fill", value="abc", descriptor=_field("#q", name="q")),
    ]
    steps, _, _, _ = events_to_steps(events)
    assert steps == [{"action": "fill", "selector": "#q", "value": "abc"}]


def test_navigation_following_a_click_is_dropped_but_the_first_is_kept() -> None:
    events = [
        RecordedEvent(kind="navigate", url="https://site/login"),
        RecordedEvent(kind="click", descriptor=_field("#submit")),
        RecordedEvent(kind="navigate", url="https://site/dashboard"),  # caused by the click
    ]
    steps, _, _, _ = events_to_steps(events)
    assert [s["action"] for s in steps] == ["navigate", "click"]
    assert steps[0]["url"] == "https://site/login"


def test_manual_navigation_not_preceded_by_a_click_is_kept() -> None:
    events = [
        RecordedEvent(kind="navigate", url="https://site/a"),
        RecordedEvent(kind="navigate", url="https://site/b"),  # typed in the address bar
    ]
    steps, _, _, _ = events_to_steps(events)
    assert [s["url"] for s in steps] == ["https://site/a", "https://site/b"]


def test_link_click_becomes_a_navigate_to_its_url() -> None:
    # Clicking a link is replayed as a navigate (stable URL), not a fragile selector click.
    events = [
        RecordedEvent(kind="navigate", url="https://site/list"),
        RecordedEvent(kind="click", url="https://site/item/42", descriptor=_field("a.row-link")),
    ]
    steps, _, _, _ = events_to_steps(events)
    assert [s["action"] for s in steps] == ["navigate", "navigate"]
    assert steps[1] == {"action": "navigate", "url": "https://site/item/42"}


def test_button_click_without_a_url_stays_a_click() -> None:
    steps, _, _, _ = events_to_steps([RecordedEvent(kind="click", descriptor=_field("#submit"))])
    assert steps == [{"action": "click", "selector": "#submit"}]


def test_select_and_press_map_to_their_actions() -> None:
    events = [
        RecordedEvent(kind="select", value="FR", descriptor=_field("#country", name="country")),
        RecordedEvent(kind="press", key="Enter", descriptor=_field("#country", name="country")),
    ]
    steps, _, _, _ = events_to_steps(events)
    assert steps[0] == {"action": "select", "selector": "#country", "value": "FR"}
    assert steps[1] == {"action": "press", "key": "Enter", "selector": "#country"}


def test_text_selector_type_is_emitted_but_css_default_is_omitted() -> None:
    text_target = ElementDescriptor(
        tag="button", css_path="b", candidates=(Candidate("text", "Log in", "text", True),)
    )
    css_target = ElementDescriptor(
        tag="button", css_path="b", candidates=(Candidate("id", "#go", "css", True),)
    )
    steps, _, _, _ = events_to_steps(
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
    _, secrets, _, _ = events_to_steps(events)
    assert secrets == ["secret", "secret_2"]


# ── extraction (overlay picks) ───────────────────────────────────────────────
def test_wait_for_maps_to_a_wait_step() -> None:
    steps, _, _, _ = events_to_steps([RecordedEvent(kind="wait_for", descriptor=_field(".quote"))])
    assert steps == [{"action": "wait_for", "selector": ".quote"}]


def test_single_and_list_picks_coalesce_into_one_extract_with_outputs() -> None:
    events = [
        RecordedEvent(
            kind="extract", descriptor=_field("h1"), config={"name": "title", "as": "text"}
        ),
        RecordedEvent(
            kind="extract", descriptor=_field(".tag"), config={"name": "tags", "as": "list"}
        ),
    ]
    steps, _, _, outputs = events_to_steps(events)
    assert len(steps) == 1
    assert steps[0]["action"] == "extract" and steps[0]["id"] == "data"
    assert steps[0]["outputs"] == {
        "title": {"selector": "h1", "as": "text"},
        "tags": {"selector": ".tag", "as": "list"},
    }
    assert outputs == {"title": "{{ steps.data.title }}", "tags": "{{ steps.data.tags }}"}


def test_records_pick_builds_each_and_relative_fields() -> None:
    event = RecordedEvent(
        kind="extract_records",
        descriptor=_field(".quote"),
        config={
            "name": "quotes",
            "fields": [
                {"name": "text", "selector": ".text", "as": "text"},
                {"name": "author", "selector": ".author", "as": "text"},
            ],
        },
    )
    steps, _, _, outputs = events_to_steps([event])
    assert steps[0]["outputs"]["quotes"] == {
        "each": ".quote",
        "fields": {
            "text": {"selector": ".text", "as": "text"},
            "author": {"selector": ".author", "as": "text"},
        },
    }
    assert outputs == {"quotes": "{{ steps.data.quotes }}"}


def test_an_action_between_picks_starts_a_second_extract_step() -> None:
    events = [
        RecordedEvent(kind="extract", descriptor=_field("h1"), config={"name": "a", "as": "text"}),
        RecordedEvent(kind="click", descriptor=_field("#next")),
        RecordedEvent(kind="extract", descriptor=_field("h2"), config={"name": "b", "as": "text"}),
    ]
    steps, _, _, outputs = events_to_steps(events)
    ids = [s["id"] for s in steps if s["action"] == "extract"]
    assert ids == ["data", "data_2"]
    assert outputs["b"] == "{{ steps.data_2.b }}"


def test_parameterize_rewrites_the_matching_fill_into_an_input() -> None:
    events = [
        RecordedEvent(kind="fill", value="TP-A1", descriptor=_field("#group", name="group")),
        RecordedEvent(
            kind="parameterize",
            descriptor=_field("#group", name="group"),
            config={"name": "groupe"},
        ),
    ]
    steps, _, inputs, _ = events_to_steps(events)
    assert steps[0]["value"] == "{{ inputs.groupe }}"
    assert inputs == {"groupe": {"type": "string", "required": True}}


def test_parameterize_infers_type_and_format_from_html_type() -> None:
    events = [
        RecordedEvent(kind="fill", value="2026-02-02", descriptor=_field("#d", field_type="date")),
        RecordedEvent(
            kind="parameterize", descriptor=_field("#d", field_type="date"), config={"name": "day"}
        ),
        RecordedEvent(kind="fill", value="3", descriptor=_field("#n", field_type="number")),
        RecordedEvent(
            kind="parameterize",
            descriptor=_field("#n", field_type="number"),
            config={"name": "qty"},
        ),
    ]
    _, _, inputs, _ = events_to_steps(events)
    assert inputs["day"] == {"type": "string", "format": "date", "required": True}
    assert inputs["qty"] == {"type": "number", "required": True}


def test_parameterize_leaves_a_secret_alone() -> None:
    events = [
        RecordedEvent(kind="fill", redacted=True, descriptor=_field("#pw", name="password")),
        RecordedEvent(
            kind="parameterize", descriptor=_field("#pw", name="password"), config={"name": "x"}
        ),
    ]
    steps, secrets, inputs, _ = events_to_steps(events)
    assert steps[0]["value"] == "{{ secrets.password }}"
    assert inputs == {}  # a secret is not turned into an input


# ── assembly ─────────────────────────────────────────────────────────────────
def test_assemble_blueprint_is_minimal_and_ordered() -> None:
    bp = assemble_blueprint("quotes.login", [{"action": "navigate", "url": "u"}], ["password"])
    assert list(bp.keys()) == ["aetherius", "name", "act", "secrets", "steps"]

    no_secrets = assemble_blueprint("x", [{"action": "navigate", "url": "u"}], [])
    assert "secrets" not in no_secrets  # omitted when empty


def test_assemble_blueprint_places_inputs_and_outputs_in_schema_order() -> None:
    bp = assemble_blueprint(
        "s",
        [{"action": "navigate", "url": "u"}],
        ["pw"],
        inputs={"g": {"type": "string", "required": True}},
        outputs={"x": "{{ steps.data.x }}"},
        description="d",
    )
    assert list(bp.keys()) == [
        "aetherius",
        "name",
        "description",
        "act",
        "inputs",
        "secrets",
        "steps",
        "outputs",
    ]


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

        def record(self) -> RecordingResult:
            steps, secrets, inputs, outputs = events_to_steps(canned)
            return RecordingResult(steps, secrets, inputs, outputs)

    monkeypatch.setattr(br, "RecordingSession", _FakeSession)

    path = record_blueprint("quotes.login", "https://quotes.toscrape.com/login", out_dir=tmp_path)
    assert path == tmp_path / "quotes.login.blueprint.json"

    loaded = load_blueprint(path)
    validate_for_act(loaded)  # canonical validation: must not raise
    assert set(loaded.secrets) == {"username", "password"}
    assert [s.action for s in loaded.steps] == ["navigate", "fill", "fill", "click"]

    raw = json.loads(path.read_text())
    pw_step = next(s for s in raw["steps"] if s.get("selector") == "#password")
    assert pw_step["value"] == "{{ secrets.password }}"
