"""Guided schedule form: create or edit a schedule without touching JSON.

Same validation seams as the CLI and the API (``parse_trigger``/``misfire_policy``/
``validate_notify_policy``): a broken trigger or alert policy is rejected at save time with a
readable notification, and nothing is written. Secrets take no input here — a schedule stores
secret *names* only, resolved from the environment at fire time.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, Switch

from ....config.secrets import available_from_env
from ....core.blueprint.models import Blueprint
from ....core.errors import AetheriusError
from ....notify.registry import known_kinds
from ....server.scheduler import misfire_policy, next_run_at, parse_trigger, validate_notify_policy
from ....store import ScheduleRecord, Store
from ...theme import AMBER, LAUREL, starred
from ...widgets.form import BlueprintInputForm
from ..library_scan import discover_blueprint_dirs, scan_blueprints
from ._common import get_default_store

_TRIGGER_PLACEHOLDERS: dict[str, str] = {
    "interval": "seconds between fires, e.g. 3600",
    "cron": "5-field cron, local time, e.g. 0 0,3 * * *",
    "at": "ISO datetime, e.g. 2026-07-20T08:00",
}


def _initial_trigger(trigger: dict[str, Any]) -> tuple[str, str, str]:
    """(kind, value, misfire) initial form state from a stored trigger dict."""
    kind = str(trigger.get("kind", "interval"))
    if kind == "cron":
        value = str(trigger.get("expr", ""))
    elif kind == "at":
        value = str(trigger.get("when", ""))
    else:
        value = str(trigger.get("seconds", ""))
    return kind, value, str(trigger.get("misfire", "run_once"))


class ScheduleFormScreen(Screen[None]):
    """Create a schedule (optionally pre-filled with a Blueprint) or edit an existing one."""

    def __init__(
        self,
        store: Store | None = None,
        blueprint_path: Path | None = None,
        edit: ScheduleRecord | None = None,
    ) -> None:
        super().__init__()
        self._store = store if store is not None else get_default_store()
        self._edit = edit
        # Parsed Blueprint per selectable path; the form's input fields are derived from it.
        self._models: dict[str, Blueprint | None] = {}
        for entry in scan_blueprints(discover_blueprint_dirs()):
            if entry.blueprint is not None:
                self._models[str(entry.path.resolve())] = entry.blueprint
        self._selected = self._initial_selection(blueprint_path)

    def _initial_selection(self, blueprint_path: Path | None) -> str | None:
        if self._edit is not None:
            # The stored path stays selectable even if it no longer scans (file moved/broken):
            # editing the cadence of a broken schedule must remain possible.
            self._models.setdefault(self._edit.blueprint, None)
            return self._edit.blueprint
        if blueprint_path is not None:
            return str(blueprint_path.resolve())
        return next(iter(self._models), None)

    # ── layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        edit = self._edit
        title = f"Edit schedule — {edit.name}" if edit else "New schedule"
        kind, trigger_value, misfire = _initial_trigger(edit.trigger if edit else {})
        policy = edit.notify if edit else {}

        yield Header()
        with VerticalScroll(classes="console-body"):
            yield Static(starred(title), classes="console-title")
            yield Static(
                "A schedule re-runs a Blueprint on a trigger and can alert on the outcome. "
                "It fires while a daemon runs (see docs/scheduler.md).",
                classes="console-subtitle",
            )
            if self._selected is None:
                yield Static(
                    "No Blueprint found — create one in the Studio or the Recorder first.",
                    classes="console-subtitle",
                )
                yield Footer()
                return

            with Vertical(classes="form-field"):
                yield Label("Blueprint")
                yield Select(
                    [(path, path) for path in self._models],
                    value=self._selected,
                    allow_blank=False,
                    id="sf-blueprint",
                )
            with Vertical(classes="form-field"):
                yield Label("Name")
                yield Input(
                    value=edit.name
                    if edit
                    else Path(self._selected).stem.replace(".blueprint", ""),
                    placeholder="e.g. quotes-watch",
                    id="sf-name",
                )
            with Vertical(classes="form-field"):
                yield Label("Trigger")
                with Horizontal(classes="sf-row"):
                    yield Select(
                        [("interval", "interval"), ("cron", "cron"), ("at (one-shot)", "at")],
                        value=kind,
                        allow_blank=False,
                        id="sf-kind",
                    )
                    yield Input(
                        value=trigger_value,
                        placeholder=_TRIGGER_PLACEHOLDERS[kind],
                        id="sf-trigger-value",
                    )
            with Vertical(classes="form-field"):
                yield Label("Missed fires (daemon was down)")
                yield Select(
                    [
                        ("run once — one catch-up fire (default)", "run_once"),
                        ("skip — wait for the next slot", "skip"),
                        ("run all — replay every missed slot", "run_all"),
                    ],
                    value=misfire,
                    allow_blank=False,
                    id="sf-misfire",
                )
            with Horizontal(classes="sf-row form-field"):
                yield Switch(value=edit.enabled if edit else True, id="sf-enabled")
                yield Static("Enabled — fires on its trigger", classes="sf-switch-label")

            inputs_box = Vertical(id="sf-inputs")
            inputs_box.border_title = "✦ Blueprint inputs ✦"
            yield inputs_box
            yield Static(id="sf-secrets", classes="console-subtitle")

            with Vertical(classes="form-field"):
                yield Label("Alert channel")
                yield Select(
                    [("none — no alerts", "none")] + [(kind_, kind_) for kind_ in known_kinds()],
                    value=str(policy.get("channel", "none")),
                    allow_blank=False,
                    id="sf-channel",
                )
            with Vertical(classes="form-field"):
                yield Label("Alert target (supports {{ secrets.x }})")
                yield Input(
                    value=str(policy.get("target", "")),
                    placeholder="webhook url, ntfy topic, chat id, ...",
                    id="sf-target",
                )
            with Vertical(classes="form-field"):
                yield Label("Alert on")
                yield Select(
                    [
                        ("failure (default)", "failure"),
                        ("success", "success"),
                        ("always", "always"),
                        ("change — only when outputs change", "change"),
                    ],
                    value=str(policy.get("on", "failure")),
                    allow_blank=False,
                    id="sf-on",
                )
            with Vertical(classes="form-field"):
                yield Label("Extra channel config (JSON object, optional)")
                yield Input(
                    value=json.dumps(policy["config"]) if policy.get("config") else "",
                    placeholder='e.g. {"bot_token": "{{ secrets.tg_token }}"}',
                    id="sf-config",
                )
            with Horizontal(classes="run-actions"):
                yield Button("✦ Save ✦", id="sf-save", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        if self._selected is not None:
            self._rebuild_blueprint_section()

    # ── blueprint-dependent section ───────────────────────────────────────────

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sf-kind":
            self.query_one("#sf-trigger-value", Input).placeholder = _TRIGGER_PLACEHOLDERS[
                str(event.value)
            ]
        elif event.select.id == "sf-blueprint":
            self._selected = str(event.value)
            await self.query_one("#sf-inputs", Vertical).remove_children()
            self._rebuild_blueprint_section()

    def _rebuild_blueprint_section(self) -> None:
        assert self._selected is not None
        model = self._models.get(self._selected)
        secrets_note = self.query_one("#sf-secrets", Static)
        box = self.query_one("#sf-inputs", Vertical)

        if model is None:
            box.mount(
                Static(
                    "This Blueprint file no longer parses — fix it in the Studio; "
                    "stored inputs are kept as-is.",
                    classes="console-subtitle",
                )
            )
            secrets_note.update("")
            return

        values = self._edit.inputs if self._edit is not None else None
        if model.inputs:
            box.mount(BlueprintInputForm(model.inputs, secrets=[], values=values))
        else:
            box.mount(Static("This Blueprint declares no inputs.", classes="console-subtitle"))

        if model.secrets:
            resolved = available_from_env(model.secrets)
            parts = [
                f"[{LAUREL}]{name} ✓[/]" if name in resolved else f"[{AMBER}]{name} — missing[/]"
                for name in model.secrets
            ]
            secrets_note.update("Secrets (resolved from .env at fire time): " + ", ".join(parts))
        else:
            secrets_note.update("")

    # ── save ──────────────────────────────────────────────────────────────────

    def _collect_trigger(self) -> dict[str, Any]:
        kind = str(self.query_one("#sf-kind", Select).value)
        raw = self.query_one("#sf-trigger-value", Input).value.strip()
        trigger: dict[str, Any]
        if kind == "interval":
            if not raw.isdigit():
                raise AetheriusError("Interval must be a whole number of seconds.")
            trigger = {"kind": "interval", "seconds": int(raw)}
        elif kind == "cron":
            trigger = {"kind": "cron", "expr": raw}
        else:
            trigger = {"kind": "at", "when": raw}
        misfire = str(self.query_one("#sf-misfire", Select).value)
        if misfire != "run_once":
            trigger["misfire"] = misfire
        return trigger

    def _collect_notify(self) -> dict[str, Any]:
        channel = str(self.query_one("#sf-channel", Select).value)
        if channel == "none":
            return {}
        policy: dict[str, Any] = {"channel": channel}
        target = self.query_one("#sf-target", Input).value.strip()
        if target:
            policy["target"] = target
        on = str(self.query_one("#sf-on", Select).value)
        if on != "failure":
            policy["on"] = on
        raw_config = self.query_one("#sf-config", Input).value.strip()
        if raw_config:
            try:
                config = json.loads(raw_config)
            except json.JSONDecodeError as exc:
                raise AetheriusError(f"Channel config is not valid JSON: {exc}") from exc
            policy["config"] = config
        return policy

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sf-save":
            self._save()

    def _save(self) -> None:
        assert self._selected is not None
        name = self.query_one("#sf-name", Input).value.strip()
        if not name:
            self.app.notify("A schedule needs a name.", severity="warning", timeout=6)
            return

        try:
            trigger = self._collect_trigger()
            parsed = parse_trigger(trigger)
            misfire_policy(trigger)
            notify = self._collect_notify()
            validate_notify_policy(notify)
        except AetheriusError as exc:
            self.app.notify(str(exc), severity="warning", timeout=8)
            return

        model = self._models.get(self._selected)
        try:
            form = self.query_one(BlueprintInputForm)
            inputs, _ = form.collect()
        except Exception:  # noqa: BLE001 - no inputs form mounted (no inputs / broken file)
            inputs = self._edit.inputs if self._edit is not None else {}
        secrets = (
            list(model.secrets)
            if model is not None
            else (list(self._edit.secrets) if self._edit is not None else [])
        )
        enabled = self.query_one("#sf-enabled", Switch).value
        now = datetime.now(timezone.utc)

        if self._edit is None:
            record = ScheduleRecord(
                id=uuid.uuid4().hex,
                name=name,
                blueprint=self._selected,
                inputs=inputs,
                secrets=secrets,
                trigger=trigger,
                notify=notify,
                enabled=enabled,
                created_at=now,
                next_run_at=next_run_at(parsed, now),
            )
            self._store.schedules.create(record)
            self.app.notify(f"Schedule {name!r} created.", timeout=4)
        else:
            changes: dict[str, Any] = {
                "name": name,
                "blueprint": self._selected,
                "inputs": inputs,
                "secrets": secrets,
                "trigger": trigger,
                "notify": notify,
                "enabled": enabled,
            }
            # Same rule as the API PATCH: a new rule or a resume restarts the cadence from now.
            resumed = enabled and not self._edit.enabled
            if trigger != self._edit.trigger or resumed:
                changes["next_run_at"] = next_run_at(parsed, now)
            self._store.schedules.update(self._edit.model_copy(update=changes))
            self.app.notify(f"Schedule {name!r} updated.", timeout=4)
        self.app.pop_screen()
