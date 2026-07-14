"""Tests for scheduler/triggers.py — trigger parsing and next-fire math.

Cron expressions are evaluated in the host's local timezone and returned in UTC; the ``paris_tz``
fixture pins a DST-observing zone so the wall-clock assertions are deterministic anywhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from aetherius.core.errors import ScheduleError
from aetherius.server.scheduler import Trigger, next_run_at, parse_trigger

pytestmark = pytest.mark.unit


# ── parse_trigger ─────────────────────────────────────────────────────────────


def test_parse_cron() -> None:
    trigger = parse_trigger({"kind": "cron", "expr": "0 0,3 * * *"})

    assert trigger == Trigger(kind="cron", expr="0 0,3 * * *")


@pytest.mark.parametrize("expr", ["not a cron", "* * *", "", None, 5])
def test_parse_rejects_a_bad_cron_expression(expr: Any) -> None:
    with pytest.raises(ScheduleError, match="cron"):
        parse_trigger({"kind": "cron", "expr": expr})


def test_parse_interval() -> None:
    trigger = parse_trigger({"kind": "interval", "seconds": 3600})

    assert trigger == Trigger(kind="interval", seconds=3600)


@pytest.mark.parametrize("seconds", [0, -5, "60", None, True])
def test_parse_rejects_a_bad_interval(seconds: Any) -> None:
    with pytest.raises(ScheduleError, match="seconds"):
        parse_trigger({"kind": "interval", "seconds": seconds})


def test_parse_at_normalizes_a_naive_local_datetime_to_utc(paris_tz: None) -> None:
    trigger = parse_trigger({"kind": "at", "when": "2026-07-15T08:00:00"})

    # July in Paris is UTC+2: 08:00 local is 06:00 UTC.
    assert trigger.when == datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)


def test_parse_at_keeps_an_explicit_offset() -> None:
    trigger = parse_trigger({"kind": "at", "when": "2026-07-15T08:00:00+00:00"})

    assert trigger.when == datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("when", ["yesterday", "", None, 42])
def test_parse_rejects_a_bad_at_datetime(when: Any) -> None:
    with pytest.raises(ScheduleError, match="'at'"):
        parse_trigger({"kind": "at", "when": when})


def test_parse_rejects_an_unknown_kind() -> None:
    with pytest.raises(ScheduleError, match="kind"):
        parse_trigger({"kind": "hourly"})


# ── next_run_at ───────────────────────────────────────────────────────────────


def test_cron_fires_at_local_midnight_and_three(paris_tz: None) -> None:
    trigger = parse_trigger({"kind": "cron", "expr": "0 0,3 * * *"})
    after = datetime(2026, 7, 14, 20, 0, tzinfo=timezone.utc)  # 22:00 local

    first = next_run_at(trigger, after)
    assert first == datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)  # local midnight

    second = next_run_at(trigger, first)
    assert second == datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)  # local 3am


def test_cron_survives_the_spring_forward(paris_tz: None) -> None:
    # Daily 3am local across 2026-03-29 (02:00 -> 03:00 CEST): the fire stays at 3am wall clock,
    # so the two UTC instants are 23 hours apart, not 24.
    trigger = parse_trigger({"kind": "cron", "expr": "0 3 * * *"})

    first = next_run_at(trigger, datetime(2026, 3, 28, 1, 30, tzinfo=timezone.utc))
    assert first == datetime(2026, 3, 28, 2, 0, tzinfo=timezone.utc)

    second = next_run_at(trigger, first)
    assert second == datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)
    assert second - first == timedelta(hours=23)


def test_cron_skips_months_without_the_requested_day(paris_tz: None) -> None:
    trigger = parse_trigger({"kind": "cron", "expr": "0 0 31 * *"})

    january = next_run_at(trigger, datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert january is not None and january.astimezone().day == 31

    after_january = next_run_at(trigger, january)
    assert after_january is not None
    assert after_january.astimezone().month == 3  # February has no 31st


def test_interval_adds_seconds() -> None:
    trigger = parse_trigger({"kind": "interval", "seconds": 90})
    after = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)

    assert next_run_at(trigger, after) == after + timedelta(seconds=90)


def test_at_fires_once_then_exhausts() -> None:
    when = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)
    trigger = parse_trigger({"kind": "at", "when": when.isoformat()})

    assert next_run_at(trigger, when - timedelta(hours=1)) == when
    assert next_run_at(trigger, when) is None
    assert next_run_at(trigger, when + timedelta(hours=1)) is None


def test_next_run_is_always_utc_aware() -> None:
    trigger = parse_trigger({"kind": "cron", "expr": "*/5 * * * *"})

    result = next_run_at(trigger, datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc))

    assert result is not None
    assert result.utcoffset() == timedelta(0)
