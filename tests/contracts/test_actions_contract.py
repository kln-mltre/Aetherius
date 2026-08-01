"""contracts/actions.json is a generated projection of the live action registry.

The embedded TypeScript engine (Phase 3) consumes this file instead of redeclaring the action
vocabulary; nothing else keeps the two in step, so guard them byte for byte — the same motif as
test_shipped_schema_matches_contract. When this fails, run ``make contracts`` and commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.core.actions.base import ACT_CAPABILITIES
from aetherius.core.actions.contract import CONTRACT_VERSION, render_actions_contract
from aetherius.core.actions.registry import plugin_actions

pytestmark = pytest.mark.contracts


def _contract(contracts_dir: Path) -> dict:
    return json.loads((contracts_dir / "actions.json").read_text(encoding="utf-8"))


def test_committed_contract_matches_the_registry(contracts_dir: Path) -> None:
    committed = (contracts_dir / "actions.json").read_text(encoding="utf-8")
    assert committed == render_actions_contract(), (
        "contracts/actions.json is stale — run 'make contracts' and commit the result."
    )


def test_contract_excludes_plugin_actions(contracts_dir: Path) -> None:
    # A plugin installed on the generating machine must never leak into a language-agnostic
    # contract: it would make the file depend on the local environment.
    actions = set(_contract(contracts_dir)["actions"])
    assert not (actions & plugin_actions())


def test_contract_declares_every_act_and_its_actions(contracts_dir: Path) -> None:
    contract = _contract(contracts_dir)
    assert contract["version"] == CONTRACT_VERSION
    capabilities = contract["act_capabilities"]
    assert list(capabilities) == list(ACT_CAPABILITIES), "act order carries the escalation chain"
    known = set(contract["actions"])
    for act, names in capabilities.items():
        assert set(names) <= known, f"{act} names an action absent from the contract"
