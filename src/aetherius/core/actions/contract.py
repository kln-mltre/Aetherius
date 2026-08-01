"""Project the action registry into ``contracts/actions.json``, the second engine's source.

The builder catalogue (``builder/catalog.py``) was the only projection of the registry; it is
Python-facing. This module adds a language-agnostic one, so the embedded TypeScript engine
(Phase 3) can honour the same action vocabulary without redeclaring it — the anti-drift guard of
docs/phase-3/3-a-socle-ts.md. The file is generated, never hand-edited: ``make contracts``
regenerates it and tests/contracts/test_actions_contract.py fails when the two diverge.

Only **built-in** actions are projected. Plugin actions (docs/plugins.md) are installation-specific
and act-agnostic: emitting them would make the contract depend on what happens to be installed on
the machine that ran the generator.

Dev-only utility, never imported at runtime; kept import-light like the rest of ``core.actions``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import ACT_CAPABILITIES, FLOW_ACTIONS, FLOW_NESTED_FIELDS
from .registry import builtin_action_specs
from .spec import ActionSpec

# Bumped when the *shape* of the document changes, not when an action does; consumers pin it.
CONTRACT_VERSION = "1.0"

_HEADER = (
    "Generated from the Aetherius action registry (src/aetherius/core/actions/). "
    "Do not edit by hand: run 'make contracts'."
)

# Repo root, resolved from this module so the target path never depends on the working directory
# (same idiom as console/screenshots.py).
_REPO = Path(__file__).resolve().parents[4]
CONTRACT_PATH = _REPO / "contracts" / "actions.json"


def _spec_to_json(spec: ActionSpec) -> dict[str, Any]:
    return {
        "summary": spec.summary,
        "params": [
            {
                "name": param.name,
                "kind": param.kind,
                "required": param.required,
                "default": param.default,
                "help": param.help,
                "placeholder": param.placeholder,
            }
            for param in spec.params
        ],
    }


def build_actions_contract() -> dict[str, Any]:
    """Return the contract document as a plain dict, deterministic across runs.

    Act order is the escalation order declared by ``ACT_CAPABILITIES`` and is **meaningful**: a
    consumer derives "which act introduces this action" from the first act that lists it, so the
    keys are deliberately not sorted. Everything else is.
    """
    return {
        "version": CONTRACT_VERSION,
        "description": _HEADER,
        "actions": {
            name: _spec_to_json(spec) for name, spec in sorted(builtin_action_specs().items())
        },
        "act_capabilities": {
            act: sorted(cap.value for cap in caps) for act, caps in ACT_CAPABILITIES.items()
        },
        "flow_actions": sorted(cap.value for cap in FLOW_ACTIONS),
        "flow_nested_fields": {
            action: list(fields) for action, fields in sorted(FLOW_NESTED_FIELDS.items())
        },
    }


def render_actions_contract() -> str:
    """The contract serialized exactly as it is committed (trailing newline included)."""
    return json.dumps(build_actions_contract(), indent=2, ensure_ascii=False) + "\n"


def write_actions_contract(path: Path | None = None) -> Path:
    """Write the contract to *path* (default ``contracts/actions.json``) and return it."""
    target = path or CONTRACT_PATH
    target.write_text(render_actions_contract(), encoding="utf-8")
    return target


def main() -> None:
    print(f"Wrote {write_actions_contract()}")


if __name__ == "__main__":
    main()
