"""Tests for builder/catalog.py — the Act/action projection of the registry."""

from __future__ import annotations

import pytest

from aetherius.builder.catalog import act_infos, actions_for_act, get_act_info
from aetherius.core.actions.base import ACT_CAPABILITIES
from aetherius.core.errors import BuilderError
from aetherius.core.runtime.engine import IMPLEMENTED_ACTS

pytestmark = pytest.mark.unit


def test_act_infos_lists_four_acts_in_order_with_status() -> None:
    infos = act_infos()
    assert [i.act for i in infos] == ["vector", "continuum", "oracle", "phantom"]
    for info in infos:
        assert info.implemented == (info.act in IMPLEMENTED_ACTS)


def test_actions_for_vector_cover_its_capabilities() -> None:
    infos = actions_for_act("vector")
    names = {i.spec.name for i in infos}
    assert names == {cap.value for cap in ACT_CAPABILITIES["vector"]}

    runnable = {i.spec.name: i.runnable for i in infos}
    assert runnable["http.request"] is True
    # Declared but not dispatched by the vector driver.
    assert runnable["extract"] is False
    # Flow actions are interpreted by the step executor, so they are runnable everywhere.
    assert runnable["for_each"] is True


def test_actions_for_phantom_mirror_its_runnable_status() -> None:
    # Phantom is runnable (Jalon 2-C): its actions follow the same rule as any implemented Act —
    # runnable unless listed in that Act's PENDING_ACTIONS (http.request is inherited but undriven).
    runnable = {i.spec.name: i.runnable for i in actions_for_act("phantom")}
    assert runnable["read"] is True
    assert runnable["click"] is True
    assert runnable["http.request"] is False


def test_unknown_act_raises() -> None:
    with pytest.raises(BuilderError):
        get_act_info("nope")
    with pytest.raises(BuilderError):
        actions_for_act("nope")


def test_plugin_actions_appear_under_every_act(plugin_action: str) -> None:
    # Plugin actions are act-agnostic (Jalon E): projected under each Act, runnable wherever the
    # Act itself is implemented.
    for act in ("vector", "continuum", "oracle", "phantom"):
        info = next(i for i in actions_for_act(act) if i.spec.name == plugin_action)
        assert info.runnable == (act in IMPLEMENTED_ACTS)
