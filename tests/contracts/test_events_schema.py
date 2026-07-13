"""The events emitted by a run serialize to the language-agnostic events.schema.json.

The daemon streams these over the WebSocket and the SDKs deserialize them, so the wire form is a
contract: this guards that ``event_to_wire`` keeps producing schema-conformant objects.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from aetherius.core.events.models import EventType, RunEvent
from aetherius.server.schemas import event_to_wire

pytestmark = pytest.mark.contracts


def _events_schema(contracts_dir: Path) -> dict:
    return json.loads((contracts_dir / "events.schema.json").read_text(encoding="utf-8"))


_EVENTS = [
    RunEvent(run_id="r", type=EventType.PROGRESS, message="run started", level="info"),
    RunEvent(run_id="r", type=EventType.STEP_STARTED, step_id="s1", level="debug"),
    RunEvent(run_id="r", type=EventType.STEP_FINISHED, step_id="s1", level="debug"),
    RunEvent(
        run_id="r",
        type=EventType.STEP_SKIPPED,
        step_id="s1",
        message="skipped: when '{{ steps.check.ok }}' is false",
        level="info",
        data={"when": "{{ steps.check.ok }}"},
    ),
    RunEvent(run_id="r", type=EventType.ERROR, step_id="s1", message="boom", level="error"),
    RunEvent(
        run_id="r",
        type=EventType.DONE,
        level="info",
        message="run finished: success",
        data={"status": "success", "error": None},
    ),
]


@pytest.mark.parametrize("event", _EVENTS, ids=lambda e: e.type.value)
def test_serialized_event_conforms_to_schema(event: RunEvent, contracts_dir: Path) -> None:
    jsonschema.validate(event_to_wire(event), _events_schema(contracts_dir))
