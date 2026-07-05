"""Tests for stealth/session/warmup.py — building authentic history before automation."""

from __future__ import annotations

from random import Random
from unittest.mock import MagicMock

import pytest

from aetherius.stealth.session.warmup import plan_warmup, warmup_profile

pytestmark = pytest.mark.unit


def test_plan_warmup_one_step_per_url_with_positive_dwell() -> None:
    plan = plan_warmup(["https://a.test", "https://b.test"], dwell_ms=2000.0, rng=Random(0))
    assert [s.url for s in plan.steps] == ["https://a.test", "https://b.test"]
    assert all(s.dwell_s > 0 for s in plan.steps)


def test_warmup_profile_visits_each_url_in_order() -> None:
    page = MagicMock()
    plan = plan_warmup(["https://a.test", "https://b.test"], rng=Random(1))
    warmup_profile(page, plan, sleep=lambda _: None)
    visited = [c.args[0] for c in page.goto.call_args_list]
    assert visited == ["https://a.test", "https://b.test"]
