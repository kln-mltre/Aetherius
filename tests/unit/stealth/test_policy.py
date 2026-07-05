"""Tests for stealth/policy.py — decoding options.stealth into a typed StealthPolicy."""

from __future__ import annotations

import pytest

from aetherius.core.errors import BlueprintValidationError
from aetherius.stealth.policy import OFF, build_policy

pytestmark = pytest.mark.unit


def test_none_is_the_off_policy() -> None:
    policy = build_policy(None)
    assert policy is OFF
    assert policy.is_active is False


def test_off_string_is_inactive() -> None:
    assert build_policy("off").is_active is False


def test_human_preset_enables_everything() -> None:
    policy = build_policy("human")
    assert policy.mouse == "gestures"
    assert policy.keyboard == "human"
    assert policy.scroll == "eased"
    assert policy.fingerprint == "chrome-desktop"
    assert policy.is_active is True


def test_inline_object_parsed_field_by_field() -> None:
    policy = build_policy(
        {"mouse": "gestures", "keyboard": "human", "timing": {"distraction": 0.25}}
    )
    assert policy.mouse == "gestures"
    assert policy.keyboard == "human"
    assert policy.scroll == "off"  # unspecified -> off
    assert policy.distraction == 0.25
    assert policy.fingerprint is None


def test_fingerprint_only_is_active() -> None:
    assert build_policy({"fingerprint": "chrome-desktop"}).is_active is True


def test_unknown_preset_rejected() -> None:
    with pytest.raises(BlueprintValidationError):
        build_policy("ninja")


def test_unknown_key_rejected() -> None:
    with pytest.raises(BlueprintValidationError):
        build_policy({"mouse": "gestures", "bogus": 1})


def test_bad_enum_value_rejected() -> None:
    with pytest.raises(BlueprintValidationError):
        build_policy({"keyboard": "robot"})


@pytest.mark.parametrize("bad", [-0.1, 1.5, True, "x"])
def test_bad_distraction_rejected(bad: object) -> None:
    with pytest.raises(BlueprintValidationError):
        build_policy({"timing": {"distraction": bad}})


def test_non_object_rejected() -> None:
    with pytest.raises(BlueprintValidationError):
        build_policy(42)
