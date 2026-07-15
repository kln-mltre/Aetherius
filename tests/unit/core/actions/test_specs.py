"""Anti-drift guards for the action specs (core/actions/*).

The specs the builder projects must stay a faithful, complete image of the capability table: exactly
one spec per Capability, no more, no fewer, and PENDING_ACTIONS must reference only real, supported
actions of runnable Acts.
"""

from __future__ import annotations

import pytest

from aetherius.core.actions.base import ACT_CAPABILITIES, PENDING_ACTIONS, Capability
from aetherius.core.actions.registry import action_specs, builtin_action_specs, get_spec
from aetherius.core.errors import ActionError
from aetherius.core.runtime.engine import IMPLEMENTED_ACTS

pytestmark = pytest.mark.unit


def test_specs_are_a_bijection_with_capabilities() -> None:
    # Static table only: plugin specs (Jalon E) legitimately extend action_specs() beyond the
    # Capability set, so the bijection is asserted on the built-in aggregation — robust even when
    # a real plugin is installed in the environment.
    assert set(builtin_action_specs()) == {cap.value for cap in Capability}


def test_every_spec_has_a_summary_and_unique_params() -> None:
    for name, spec in action_specs().items():
        assert spec.summary, f"{name} has no summary"
        param_names = [p.name for p in spec.params]
        assert len(param_names) == len(set(param_names)), f"{name} has duplicate params"


def test_pending_actions_reference_runnable_acts_and_real_capabilities() -> None:
    for act, pending in PENDING_ACTIONS.items():
        assert act in IMPLEMENTED_ACTS, f"{act} in PENDING_ACTIONS but not runnable"
        assert pending <= ACT_CAPABILITIES[act], f"{act} pending set exceeds its capabilities"


def test_get_spec_rejects_unknown_action() -> None:
    with pytest.raises(ActionError):
        get_spec("does.not.exist")
