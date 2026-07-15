"""Tests for plugins.py — entry-point discovery, failure isolation, idempotence (Jalon E).

Drives load_plugins() against hand-built importlib.metadata.EntryPoint objects so the real loading
path runs: ep.load() imports the target module, whose decorators register. The happy path loads the
actual demo plugin shipped in examples/plugins/ (its src goes on sys.path — no install needed),
then executes the example Blueprint against it: the full third-party story.
"""

from __future__ import annotations

import json
import logging
import sys
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Iterator

import pytest

from aetherius import plugins
from aetherius.core.actions import registry as action_registry
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.runtime.engine import RunEngine
from aetherius.notify import registry as notify_registry
from aetherius.notify.channels import WebhookChannel

pytestmark = pytest.mark.unit

_DEMO_MODULE = "aetherius_plugin_demo"


@pytest.fixture(autouse=True)
def _reset_loaded_flag() -> Iterator[None]:
    """load_plugins is process-global; each test here re-runs discovery from a clean flag."""
    yield
    plugins._loaded = False


@pytest.fixture()
def demo_plugin_on_path(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make the shipped demo plugin importable, with a clean registry slate before and after."""
    monkeypatch.syspath_prepend(
        str(repo_root / "examples" / "plugins" / "aetherius-plugin-demo" / "src")
    )
    _forget_demo_plugin()
    try:
        yield
    finally:
        _forget_demo_plugin()


def _forget_demo_plugin() -> None:
    # Drop both the registrations and the module cache: ep.load() must re-run the decorators.
    action_registry._registry.pop("demo.slugify", None)
    action_registry._plugin_specs.pop("demo.slugify", None)
    notify_registry._channels.pop("logfile", None)
    notify_registry._target_keys.pop("logfile", None)
    sys.modules.pop(_DEMO_MODULE, None)


def _patch_entry_points(
    monkeypatch: pytest.MonkeyPatch, mapping: dict[str, tuple[EntryPoint, ...]]
) -> None:
    def fake_entry_points(*, group: str) -> tuple[EntryPoint, ...]:
        return mapping.get(group, ())

    monkeypatch.setattr(plugins, "entry_points", fake_entry_points)


def _demo_entry_points() -> dict[str, tuple[EntryPoint, ...]]:
    return {
        plugins.ACTIONS_GROUP: (EntryPoint("demo", _DEMO_MODULE, plugins.ACTIONS_GROUP),),
        plugins.NOTIFY_CHANNELS_GROUP: (
            EntryPoint("demo", _DEMO_MODULE, plugins.NOTIFY_CHANNELS_GROUP),
        ),
    }


def test_load_plugins_discovers_the_demo_plugin(
    demo_plugin_on_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_entry_points(monkeypatch, _demo_entry_points())
    loaded = plugins.load_plugins(force=True)
    assert loaded == [
        f"{plugins.ACTIONS_GROUP}:demo",
        f"{plugins.NOTIFY_CHANNELS_GROUP}:demo",
    ]
    assert "demo.slugify" in action_registry.plugin_actions()
    assert "logfile" in notify_registry.known_kinds()
    assert notify_registry.target_key("logfile") == "path"


def test_the_example_blueprint_runs_against_the_demo_plugin(
    demo_plugin_on_path: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    examples_dir: Path,
) -> None:
    _patch_entry_points(monkeypatch, _demo_entry_points())
    plugins.load_plugins(force=True)

    raw = json.loads(
        (examples_dir / "plugins" / "demo-notify.blueprint.json").read_text(encoding="utf-8")
    )
    raw["vars"]["logfile"] = str(tmp_path / "alerts.log")
    result = RunEngine().run(Blueprint.model_validate(raw))

    assert result.status.value == "success"
    assert result.outputs["slug"] == "aetherius-per-nubes-ad-aethera"
    assert result.outputs["delivered"] is True
    logged = (tmp_path / "alerts.log").read_text(encoding="utf-8")
    assert "Slug ready: aetherius-per-nubes-ad-aethera" in logged


def test_a_broken_plugin_is_skipped_never_fatal(
    demo_plugin_on_path: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # One module that raises at import time, one that does not exist at all: both are contained.
    (tmp_path / "aetherius_broken_plugin.py").write_text(
        "raise RuntimeError('boom at import')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _patch_entry_points(
        monkeypatch,
        {
            plugins.ACTIONS_GROUP: (
                EntryPoint("broken", "aetherius_broken_plugin", plugins.ACTIONS_GROUP),
                EntryPoint("missing", "aetherius_missing_plugin", plugins.ACTIONS_GROUP),
                EntryPoint("demo", _DEMO_MODULE, plugins.ACTIONS_GROUP),
            )
        },
    )

    with caplog.at_level(logging.WARNING, logger="aetherius.plugins"):
        loaded = plugins.load_plugins(force=True)

    assert loaded == [f"{plugins.ACTIONS_GROUP}:demo"]
    assert "demo.slugify" in action_registry.plugin_actions()
    messages = [record.getMessage() for record in caplog.records]
    assert any("'broken'" in m for m in messages)
    assert any("'missing'" in m for m in messages)


def test_a_plugin_colliding_with_a_builtin_channel_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Built-ins load first, so the conflicting plugin is the one refused — webhook stays intact.
    (tmp_path / "aetherius_conflicting_plugin.py").write_text(
        "from aetherius.plugins import register_channel\n"
        "\n"
        "\n"
        "@register_channel('webhook')\n"
        "def build(config):\n"
        "    raise AssertionError('never built')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _patch_entry_points(
        monkeypatch,
        {
            plugins.NOTIFY_CHANNELS_GROUP: (
                EntryPoint(
                    "conflict", "aetherius_conflicting_plugin", plugins.NOTIFY_CHANNELS_GROUP
                ),
            )
        },
    )

    try:
        with caplog.at_level(logging.WARNING, logger="aetherius.plugins"):
            loaded = plugins.load_plugins(force=True)
    finally:
        sys.modules.pop("aetherius_conflicting_plugin", None)

    assert loaded == []
    assert any("'conflict'" in record.getMessage() for record in caplog.records)
    channel = notify_registry.build_channel("webhook", {"url": "https://example.test"})
    assert isinstance(channel, WebhookChannel)


def test_load_plugins_is_idempotent(
    demo_plugin_on_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_entry_points(monkeypatch, _demo_entry_points())
    assert plugins.load_plugins(force=True)
    # The second call is a no-op: no re-discovery, no duplicate-registration errors.
    assert plugins.load_plugins() == []
