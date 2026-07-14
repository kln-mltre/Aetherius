"""Tests for cli/schedule.py — the schedule command group, on an isolated temporary store."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aetherius.cli import app
from aetherius.config import settings as settings_mod
from aetherius.store import engine as engine_mod

pytestmark = pytest.mark.unit

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The CLI writes to the durable store; keep it on a temp file so no test touches the real
    # ~/.aetherius. Reset both singletons so get_store() resolves the temp database.
    monkeypatch.setenv("AETHERIUS_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()


@pytest.fixture
def selftest_path(examples_dir: Path) -> str:
    return str(examples_dir / "vector" / "daemon-selftest.blueprint.json")


def _add(selftest_path: str, *extra: str, name: str = "watch") -> str:
    result = runner.invoke(app, ["schedule", "add", name, "--blueprint", selftest_path, *extra])
    assert result.exit_code == 0, result.stdout
    return result.stdout


def test_add_creates_a_persistent_schedule(selftest_path: str) -> None:
    output = _add(selftest_path, "--every", "60", "--input", "subject=cli")

    assert "Created" in output
    schedules = engine_mod.get_store().schedules.all()
    assert len(schedules) == 1
    record = schedules[0]
    assert record.trigger == {"kind": "interval", "seconds": 60}
    assert record.inputs == {"subject": "cli"}
    assert record.next_run_at is not None
    assert Path(record.blueprint).is_absolute()


def test_add_carries_the_notify_policy_and_misfire(selftest_path: str) -> None:
    _add(
        selftest_path,
        "--cron",
        "0 0,3 * * *",
        "--misfire",
        "skip",
        "--notify",
        "ntfy",
        "--notify-target",
        "{{ secrets.topic }}",
        "--notify-on",
        "change",
    )

    record = engine_mod.get_store().schedules.all()[0]
    assert record.trigger["misfire"] == "skip"
    assert record.notify == {"channel": "ntfy", "target": "{{ secrets.topic }}", "on": "change"}


def test_add_requires_exactly_one_trigger(selftest_path: str) -> None:
    none = runner.invoke(app, ["schedule", "add", "w", "--blueprint", selftest_path])
    both = runner.invoke(
        app,
        [
            "schedule",
            "add",
            "w",
            "--blueprint",
            selftest_path,
            "--every",
            "60",
            "--cron",
            "* * * * *",
        ],
    )

    assert none.exit_code != 0
    assert both.exit_code != 0


def test_add_rejects_a_bad_cron_expression(selftest_path: str) -> None:
    result = runner.invoke(
        app, ["schedule", "add", "w", "--blueprint", selftest_path, "--cron", "nope"]
    )

    assert result.exit_code == 1
    assert "cron" in result.stdout


def test_add_rejects_an_unknown_notify_channel(selftest_path: str) -> None:
    result = runner.invoke(
        app,
        ["schedule", "add", "w", "--blueprint", selftest_path, "--every", "60", "--notify", "nope"],
    )

    assert result.exit_code == 1
    assert "Unknown notification channel" in result.stdout


def test_add_fails_fast_on_a_missing_blueprint() -> None:
    result = runner.invoke(
        app, ["schedule", "add", "w", "--blueprint", "/nonexistent.json", "--every", "60"]
    )

    assert result.exit_code == 1


def test_list_shows_the_schedule(selftest_path: str) -> None:
    _add(selftest_path, "--every", "60")

    result = runner.invoke(app, ["schedule", "list"])

    assert result.exit_code == 0
    assert "watch" in result.stdout
    assert "every 60s" in result.stdout


def test_pause_and_resume_by_name(selftest_path: str) -> None:
    _add(selftest_path, "--every", "60")
    store = engine_mod.get_store()

    paused = runner.invoke(app, ["schedule", "pause", "watch"])
    assert paused.exit_code == 0
    assert store.schedules.all()[0].enabled is False

    resumed = runner.invoke(app, ["schedule", "resume", "watch"])
    assert resumed.exit_code == 0
    record = store.schedules.all()[0]
    assert record.enabled is True
    assert record.next_run_at is not None


def test_rm_deletes_the_schedule(selftest_path: str) -> None:
    _add(selftest_path, "--every", "60")

    result = runner.invoke(app, ["schedule", "rm", "watch"])

    assert result.exit_code == 0
    assert engine_mod.get_store().schedules.all() == []


def test_an_unknown_ident_errors_cleanly() -> None:
    result = runner.invoke(app, ["schedule", "rm", "ghost"])

    assert result.exit_code == 1
    assert "Unknown schedule" in result.stdout


def test_an_ambiguous_name_asks_for_the_id(selftest_path: str) -> None:
    _add(selftest_path, "--every", "60")
    _add(selftest_path, "--every", "120")

    result = runner.invoke(app, ["schedule", "pause", "watch"])

    assert result.exit_code == 1
    assert "ambiguous" in result.stdout


def test_run_fires_in_process_and_records_history(selftest_path: str) -> None:
    _add(selftest_path, "--every", "3600", "--input", "subject=manual")
    store = engine_mod.get_store()
    schedule = store.schedules.all()[0]
    cadence = schedule.next_run_at

    result = runner.invoke(app, ["schedule", "run", "watch"])

    assert result.exit_code == 0, result.stdout
    assert "success" in result.stdout
    runs = store.runs.recent(schedule_id=schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].outputs["greeting"] == "hello, manual"
    # A manual fire leaves the cadence untouched.
    assert store.schedules.all()[0].next_run_at == cadence


def test_run_records_a_failure_when_the_blueprint_disappears(selftest_path: str) -> None:
    _add(selftest_path, "--every", "3600")
    store = engine_mod.get_store()
    schedule = store.schedules.all()[0]
    store.schedules.update(schedule.model_copy(update={"blueprint": "/vanished.json"}))

    result = runner.invoke(app, ["schedule", "run", "watch"])

    assert result.exit_code == 1
    runs = store.runs.recent(schedule_id=schedule.id)
    assert len(runs) == 1 and runs[0].status == "failed"
