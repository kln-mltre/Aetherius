"""Tests for scheduler/misfire.py — policies for fire times missed while the daemon was down."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aetherius.core.errors import ScheduleError
from aetherius.server.scheduler import (
    MisfirePolicy,
    misfire_policy,
    parse_trigger,
    resolve_misfires,
)

pytestmark = pytest.mark.unit

_TRIGGER = parse_trigger({"kind": "interval", "seconds": 60})
_DUE = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_policy_defaults_to_run_once() -> None:
    assert misfire_policy({"kind": "interval", "seconds": 60}) is MisfirePolicy.RUN_ONCE


def test_policy_reads_the_trigger_dict() -> None:
    assert misfire_policy({"kind": "cron", "misfire": "skip"}) is MisfirePolicy.SKIP


def test_policy_rejects_an_unknown_value() -> None:
    with pytest.raises(ScheduleError, match="misfire"):
        misfire_policy({"misfire": "retry-forever"})


def test_skip_fires_nothing() -> None:
    now = _DUE + timedelta(hours=1)

    assert resolve_misfires(_TRIGGER, _DUE, now, MisfirePolicy.SKIP) == []


def test_run_once_coalesces_the_gap_into_one_catchup() -> None:
    now = _DUE + timedelta(hours=1)

    assert resolve_misfires(_TRIGGER, _DUE, now, MisfirePolicy.RUN_ONCE) == [_DUE]


def test_run_all_replays_every_missed_slot() -> None:
    now = _DUE + timedelta(minutes=3, seconds=30)

    fires = resolve_misfires(_TRIGGER, _DUE, now, MisfirePolicy.RUN_ALL)

    assert fires == [_DUE + timedelta(minutes=n) for n in range(4)]


def test_run_all_is_capped_keeping_the_most_recent_slots() -> None:
    trigger = parse_trigger({"kind": "interval", "seconds": 1})
    now = _DUE + timedelta(seconds=1000)

    fires = resolve_misfires(trigger, _DUE, now, MisfirePolicy.RUN_ALL)

    assert len(fires) == 100
    assert fires[-1] == now  # the most recent slots survive, the oldest are dropped
