"""The ``aetherius schedule`` command group: persistent schedule CRUD plus a manual fire.

The CLI writes directly to the durable store (the same SQLite file the daemon polls each tick), so
managing schedules works whether the daemon is up or not — no IPC client needed. ``schedule run``
executes in-process, exactly like ``aetherius run``, but records the run against the schedule and
applies its alert policy; the schedule's cadence (``next_run_at``) is deliberately left untouched.

Heavy imports stay inside the commands, matching the rest of the CLI.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from ._shared import parse_pairs

if TYPE_CHECKING:
    from ..store import ScheduleRecord, Store

schedule_app = typer.Typer(
    help="Re-run a Blueprint on a cron, interval or one-shot trigger (see docs/scheduler.md)."
)


def _fail(message: str) -> typer.Exit:
    from rich.console import Console as RichConsole

    RichConsole().print(f"[bold red]Error:[/bold red] {message}")
    return typer.Exit(1)


def _resolve(store: "Store", ident: str) -> "ScheduleRecord":
    """Find a schedule by id or unique name; exit with a clear error otherwise."""
    record = store.schedules.get(ident)
    if record is not None:
        return record
    matches = [candidate for candidate in store.schedules.all() if candidate.name == ident]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise _fail(f"Unknown schedule {ident!r} (not an id, and no schedule has that name).")
    raise _fail(f"Schedule name {ident!r} is ambiguous ({len(matches)} matches); use the id.")


def _local(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S") if value is not None else "-"


@schedule_app.command()
def add(
    name: str,
    blueprint: Path = typer.Option(..., "--blueprint", help="Blueprint file to re-run."),
    cron: str | None = typer.Option(None, "--cron", help="5-field cron expression, local time."),
    every: int | None = typer.Option(None, "--every", help="Interval between fires, in seconds."),
    at: str | None = typer.Option(None, "--at", help="One-shot ISO datetime (local if naive)."),
    input: list[str] = typer.Option([], "--input", help="Blueprint input as key=value."),
    secret: list[str] = typer.Option(
        [], "--secret", help="Secret NAME resolved from the environment at fire time."
    ),
    notify: str | None = typer.Option(
        None, "--notify", help="Alert channel kind: webhook, discord, telegram, ntfy."
    ),
    notify_target: str | None = typer.Option(
        None, "--notify-target", help="Channel address; may reference {{ secrets.x }}."
    ),
    notify_config: list[str] = typer.Option(
        [], "--notify-config", help="Extra channel config as key=value (multi-key channels)."
    ),
    notify_on: str = typer.Option(
        "failure", "--notify-on", help="Alert policy: failure, success, always or change."
    ),
    misfire: str = typer.Option(
        "run_once", "--misfire", help="Missed-fire policy: skip, run_once or run_all."
    ),
    disabled: bool = typer.Option(False, "--disabled", help="Create the schedule paused."),
) -> None:
    """Create a persistent schedule (exactly one of --cron, --every, --at)."""
    from rich.console import Console as RichConsole

    from ..core.blueprint.loader import load_blueprint
    from ..core.errors import AetheriusError
    from ..server.scheduler import (
        misfire_policy,
        next_run_at,
        parse_trigger,
        validate_notify_policy,
    )
    from ..store import ScheduleRecord, get_store

    if sum(option is not None for option in (cron, every, at)) != 1:
        raise typer.BadParameter("Provide exactly one of --cron, --every or --at.")
    trigger: dict[str, object] = (
        {"kind": "cron", "expr": cron}
        if cron is not None
        else {"kind": "interval", "seconds": every}
        if every is not None
        else {"kind": "at", "when": at}
    )
    if misfire != "run_once":
        trigger["misfire"] = misfire

    policy: dict[str, object] = {}
    if notify is not None:
        policy["channel"] = notify
        if notify_target is not None:
            policy["target"] = notify_target
        if notify_config:
            policy["config"] = parse_pairs(notify_config, label="--notify-config")
        if notify_on != "failure":
            policy["on"] = notify_on
    elif notify_target or notify_config or notify_on != "failure":
        raise typer.BadParameter("--notify-target/--notify-config/--notify-on require --notify.")

    # Fail fast on what would otherwise only surface at fire time: a bad trigger or policy, or a
    # Blueprint that does not load. The path is stored absolute so the daemon's cwd is irrelevant.
    blueprint_path = blueprint.expanduser().resolve()
    now = datetime.now(timezone.utc)
    try:
        parsed = parse_trigger(trigger)
        misfire_policy(trigger)
        validate_notify_policy(policy)
        load_blueprint(blueprint_path)
    except AetheriusError as exc:
        raise _fail(str(exc)) from exc

    record = ScheduleRecord(
        id=uuid.uuid4().hex,
        name=name,
        blueprint=str(blueprint_path),
        inputs=parse_pairs(input, label="--input"),
        secrets=list(secret),
        trigger=trigger,
        notify=policy,
        enabled=not disabled,
        created_at=now,
        next_run_at=next_run_at(parsed, now),
    )
    get_store().schedules.create(record)
    state = "paused" if disabled else f"next run {_local(record.next_run_at)}"
    RichConsole().print(f"[bold green]Created[/bold green] {record.id} ({name}) — {state}.")


@schedule_app.command(name="list")
def list_schedules() -> None:
    """List every schedule with its trigger and next fire time."""
    from rich.console import Console as RichConsole
    from rich.table import Table

    from ..server.scheduler import describe_trigger
    from ..store import get_store

    table = Table(title="Schedules")
    for column in ("ID", "Name", "Trigger", "Enabled", "Next run", "Last run"):
        table.add_column(column)
    for record in get_store().schedules.all():
        table.add_row(
            record.id,
            record.name,
            describe_trigger(record.trigger),
            "yes" if record.enabled else "no",
            _local(record.next_run_at) if record.enabled else "-",
            _local(record.last_run_at),
        )
    RichConsole().print(table)


@schedule_app.command()
def rm(ident: str) -> None:
    """Delete a schedule by id or name."""
    from rich.console import Console as RichConsole

    from ..store import get_store

    store = get_store()
    record = _resolve(store, ident)
    store.schedules.delete(record.id)
    RichConsole().print(f"[bold green]Deleted[/bold green] {record.id} ({record.name}).")


@schedule_app.command()
def pause(ident: str) -> None:
    """Pause a schedule; it keeps its definition but stops firing."""
    from rich.console import Console as RichConsole

    from ..store import get_store

    store = get_store()
    record = _resolve(store, ident)
    store.schedules.update(record.model_copy(update={"enabled": False}))
    RichConsole().print(f"[bold green]Paused[/bold green] {record.id} ({record.name}).")


@schedule_app.command()
def resume(ident: str) -> None:
    """Resume a paused schedule; its cadence restarts from now (no catch-up of the pause)."""
    from rich.console import Console as RichConsole

    from ..core.errors import AetheriusError
    from ..server.scheduler import next_run_at, parse_trigger
    from ..store import get_store

    store = get_store()
    record = _resolve(store, ident)
    try:
        upcoming = next_run_at(parse_trigger(record.trigger), datetime.now(timezone.utc))
    except AetheriusError as exc:
        raise _fail(str(exc)) from exc
    store.schedules.update(record.model_copy(update={"enabled": True, "next_run_at": upcoming}))
    RichConsole().print(
        f"[bold green]Resumed[/bold green] {record.id} ({record.name}) — "
        f"next run {_local(upcoming)}."
    )


@schedule_app.command()
def run(ident: str) -> None:
    """Fire a schedule immediately, in-process, without touching its cadence."""
    from rich.console import Console as RichConsole

    from ..core.errors import AetheriusError
    from ..core.runtime.result import RunStatus
    from ..server.scheduler import fire_schedule
    from ..store import get_store

    rich_console = RichConsole()
    store = get_store()
    record = _resolve(store, ident)
    try:
        # Same contract as a tick-driven fire: the outcome (even a load failure) lands in the
        # history under the schedule's id and the alert policy applies.
        result, delivered = fire_schedule(record, store)
    except AetheriusError as exc:
        raise _fail(str(exc)) from exc

    alert = "no alert" if delivered is None else ("alert sent" if delivered else "alert failed")
    rich_console.print(
        f"Run {result.run_id}: [bold]{result.status.value}[/bold] "
        f"in {result.duration_ms:.1f} ms — {alert}."
    )
    # A partial run (Jalon 3-J) exits 0: it lost an optional reading, not the run. Only a hard
    # failure is a non-zero exit.
    if result.status.value == RunStatus.FAILED.value:
        raise typer.Exit(1)
