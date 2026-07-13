"""Tests for builder/factory.py — draft assembly, validation and saving."""

from __future__ import annotations

from pathlib import Path

import pytest

from aetherius.builder.factory import (
    BlueprintDraft,
    StepDraft,
    assemble_blueprint,
    build_blueprint,
    save_blueprint,
    slugify_name,
)
from aetherius.builder.validation import validate_draft
from aetherius.core.blueprint.loader import load_blueprint
from aetherius.core.errors import BlueprintSchemaError, BuilderError

pytestmark = pytest.mark.unit


def test_slugify_keeps_dots_and_strips_unsafe() -> None:
    assert slugify_name("quotes.login") == "quotes.login"
    assert slugify_name("a b/c") == "a-b-c"
    assert slugify_name("///") == "blueprint"


def test_assemble_blueprint_is_minimal_and_ordered() -> None:
    bp = assemble_blueprint("x", [{"action": "navigate", "url": "u"}], ["password"])
    assert list(bp.keys()) == ["aetherius", "name", "act", "secrets", "steps"]
    assert "secrets" not in assemble_blueprint("x", [{"action": "navigate", "url": "u"}], [])


def test_to_data_and_from_data_round_trip_all_fields() -> None:
    draft = BlueprintDraft(
        name="t.demo",
        act="continuum",
        description="d",
        inputs={"g": {"type": "string", "required": True}},
        secrets=["password"],
        vars={"domain": "https://x"},
        options={"debug": True, "session": {"profile": "p", "persist": True}},
        steps=[StepDraft(action="navigate", id="go", params={"url": "https://x"})],
        outputs={"r": "{{ steps.go.url }}"},
    )
    data = draft.to_data()
    assert BlueprintDraft.from_data(data).to_data() == data


def test_add_step_prefills_required_params_and_inserts() -> None:
    draft = BlueprintDraft(name="t", act="continuum")
    step = draft.add_step("fill")
    assert set(step.params) == {"selector", "value"}  # both required
    draft.add_step("navigate", index=0)
    assert draft.steps[0].action == "navigate"


def test_move_step_clamps_at_bounds() -> None:
    draft = BlueprintDraft(name="t", act="continuum")
    draft.add_step("navigate")
    draft.add_step("click")
    draft.move_step(0, 5)
    assert [s.action for s in draft.steps] == ["click", "navigate"]


def test_validate_draft_flags_errors_and_warnings() -> None:
    empty = validate_draft(BlueprintDraft())
    assert any(i.severity == "error" for i in empty)

    cross = BlueprintDraft(name="x.y", act="vector")
    cross.add_step("navigate")
    messages = [i.message for i in validate_draft(cross)]
    assert any("not supported by act" in m for m in messages)

    pend = BlueprintDraft(name="x.y", act="continuum")
    pend.add_step("navigate").params["url"] = "https://a"
    pend.add_step("notify")
    assert any(i.severity == "warning" and "runnable" in i.message for i in validate_draft(pend))

    missing = BlueprintDraft(name="x.y", act="continuum")
    missing.add_step("navigate")  # url left empty
    assert any(i.path.endswith("url") for i in validate_draft(missing))


def test_valid_draft_has_no_issues() -> None:
    draft = BlueprintDraft(name="t.ok", act="vector")
    draft.steps.append(
        StepDraft(action="http.request", id="f", params={"url": "https://x", "method": "GET"})
    )
    assert validate_draft(draft) == []


def test_build_blueprint_raises_on_invalid() -> None:
    with pytest.raises(BlueprintSchemaError):
        build_blueprint(BlueprintDraft())


def test_save_blueprint_writes_and_reloads(tmp_path: Path) -> None:
    draft = BlueprintDraft(name="t.save", act="vector")
    draft.steps.append(StepDraft(action="http.request", params={"url": "https://x"}))
    path = save_blueprint(draft, out_dir=tmp_path)
    assert path.name == "t.save.blueprint.json"
    assert load_blueprint(path).name == "t.save"


def test_save_blueprint_refuses_to_clobber_a_different_file(tmp_path: Path) -> None:
    draft = BlueprintDraft(name="t.save", act="vector")
    draft.steps.append(StepDraft(action="http.request", params={"url": "https://x"}))
    save_blueprint(draft, out_dir=tmp_path)
    with pytest.raises(BuilderError):
        save_blueprint(draft, out_dir=tmp_path)


def test_save_blueprint_path_overwrites_in_place(tmp_path: Path) -> None:
    target = tmp_path / "edited.blueprint.json"
    draft = BlueprintDraft(name="t.edit", act="vector")
    draft.steps.append(StepDraft(action="http.request", params={"url": "https://x"}))
    save_blueprint(draft, path=target)
    draft.description = "changed"
    save_blueprint(draft, path=target)  # no collision error in edit mode
    assert load_blueprint(target).description == "changed"
