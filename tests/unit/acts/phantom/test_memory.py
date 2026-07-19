"""Tests for acts/phantom/memory.py — history, facts, and the compact transcript."""

from __future__ import annotations

import pytest

from aetherius.acts.phantom.memory import AgentMemory

pytestmark = pytest.mark.unit


def test_record_appends_action_observation_pairs() -> None:
    memory = AgentMemory(goal="find X")
    memory.record({"action": "click", "target": {"vision": "the Login link"}}, {})
    memory.record({"action": "read", "vision": "the price"}, {"price": "£10"})

    assert len(memory.history) == 2
    assert memory.history[0]["action"]["action"] == "click"
    assert memory.history[1]["observation"] == {"price": "£10"}


def test_transcript_summarizes_actions_and_observations() -> None:
    memory = AgentMemory(goal="g")
    memory.record({"action": "navigate", "url": "https://example.com"}, {})
    memory.record({"action": "click", "target": {"vision": "the Next button"}}, {})
    memory.record({"action": "read", "vision": "the title"}, {"title": "Hello"})

    transcript = memory.transcript()

    lines = transcript.splitlines()
    assert lines[0].startswith("1. navigate 'https://example.com'")
    assert "click 'the Next button' -> ok" in lines[1]
    assert '"title": "Hello"' in lines[2]


def test_transcript_marks_failed_observations() -> None:
    memory = AgentMemory(goal="g")
    memory.record({"action": "click", "target": {"vision": "a ghost"}}, {"error": "not on screen"})

    assert "FAILED: not on screen" in memory.transcript()


def test_transcript_truncates_long_observations() -> None:
    memory = AgentMemory(goal="g")
    memory.record({"action": "read", "vision": "everything"}, {"blob": "x" * 5000})

    line = memory.transcript()
    assert "…" in line
    assert len(line) < 1000  # capped well below the raw 5000-char observation


def test_empty_transcript_is_blank() -> None:
    assert AgentMemory(goal="g").transcript() == ""
