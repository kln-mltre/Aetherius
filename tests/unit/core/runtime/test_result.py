"""Tests for core/runtime/result.py"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aetherius.core.runtime.result import Result, RunStatus, StepResult

pytestmark = pytest.mark.unit

_NOW = datetime.now(timezone.utc)


def test_run_status_values() -> None:
    assert RunStatus.SUCCESS == "success"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.PARTIAL == "partial"


def test_result_duration_ms() -> None:
    from datetime import timedelta

    started = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=2.5)
    result = Result(
        run_id="abc",
        blueprint_name="test",
        status=RunStatus.SUCCESS,
        started_at=started,
        finished_at=finished,
    )
    assert abs(result.duration_ms - 2500.0) < 1


def test_step_result_model() -> None:
    sr = StepResult(
        step_id="step1",
        action="http.request",
        status=RunStatus.SUCCESS,
        outputs={"status_code": 200},
        duration_ms=123.4,
    )
    assert sr.error is None
    assert sr.outputs["status_code"] == 200
