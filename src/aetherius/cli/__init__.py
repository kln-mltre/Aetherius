"""Command-line entry point.

Running ``aetherius`` with no argument opens the interactive Console (the terminal control center).
Subcommands (``run``, ``validate``, ``serve``, ``record``, ``schedule …``) are the scriptable,
non-interactive paths; command groups beyond the core verbs live in their own module of this
package (``schedule.py`` for the scheduler CRUD).

Kept dependency-light on purpose: heavy imports (Textual for the Console, the Aetherius facade)
happen inside the relevant command, not at module import time.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ._shared import parse_pairs
from .schedule import schedule_app

app = typer.Typer(add_completion=False, no_args_is_help=False)
app.add_typer(schedule_app, name="schedule")


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Load installed plugins, then dispatch to the Console when no subcommand is given."""
    # Every command needs the plugins loaded (run/validate accept plugin actions, schedule and the
    # Console list plugin notify channels); one idempotent call here covers them all.
    from ..plugins import load_plugins

    load_plugins()
    if ctx.invoked_subcommand is None:
        console()


@app.command()
def console() -> None:
    """Open the interactive terminal Console."""
    from ..console.app import AetheriusConsoleApp

    AetheriusConsoleApp().run()


@app.command()
def run(
    blueprint: Path,
    input: list[str] = typer.Option([], "--input", help="Blueprint input as key=value."),
    secret: list[str] = typer.Option([], "--secret", help="Runtime secret as key=value."),
    debug: bool = typer.Option(False, "--debug", help="Force verbose step-by-step logging."),
) -> None:
    """Execute a Blueprint file and print its result."""
    from rich.console import Console as RichConsole
    from rich.table import Table

    from ..core.blueprint.loader import load_blueprint
    from ..core.errors import AetheriusError
    from ..core.events.sinks import LogSink, Sink
    from ..core.runtime.approvals import ApprovalRegistry
    from ..core.runtime.engine import RunEngine
    from .approvals import StdinApprovalSink

    rich_console = RichConsole()
    inputs = parse_pairs(input, label="--input")
    secrets = parse_pairs(secret, label="--secret")

    # Human-in-the-loop (Jalon 2-E): a confirm step parks the run and prompts on stdin.
    registry = ApprovalRegistry()
    sinks: list[Sink] = [StdinApprovalSink(registry)]

    try:
        loaded = load_blueprint(blueprint)
        if debug:
            loaded.options.debug = True
            sinks.append(LogSink(debug=True))
        result = RunEngine().run(
            loaded, inputs=inputs, secrets=secrets, sinks=sinks, approvals=registry
        )
    except AetheriusError as exc:
        rich_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title=f"{result.blueprint_name} ({result.run_id})")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Status", result.status.value)
    table.add_row("Duration", f"{result.duration_ms:.1f} ms")
    if result.error:
        table.add_row("Error", result.error)
    rich_console.print(table)

    steps = Table(title="Steps")
    steps.add_column("Step")
    steps.add_column("Action")
    steps.add_column("Status")
    steps.add_column("Duration")
    for step in result.step_results:
        steps.add_row(
            step.step_id or "-", step.action, step.status.value, f"{step.duration_ms:.1f} ms"
        )
    rich_console.print(steps)

    if result.outputs:
        rich_console.print("[bold]Outputs:[/bold]")
        rich_console.print(json.dumps(result.outputs, indent=2, default=str))

    if result.status.value != "success":
        raise typer.Exit(1)


@app.command()
def validate(blueprint: Path) -> None:
    """Load a Blueprint and check it against the schema and its Act's capabilities."""
    from rich.console import Console as RichConsole

    from ..core.blueprint.loader import load_blueprint
    from ..core.blueprint.validator import validate_for_act
    from ..core.errors import AetheriusError

    rich_console = RichConsole()
    try:
        loaded = load_blueprint(blueprint)
        validate_for_act(loaded)
    except AetheriusError as exc:
        rich_console.print(f"[bold red]Invalid:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    rich_console.print(
        f"[bold green]OK[/bold green] act={loaded.act!r}, "
        f"{len(loaded.steps)} step(s), {len(loaded.inputs)} input(s)."
    )


@app.command()
def serve(
    host: str | None = typer.Option(None, "--host", help="Bind address (default 127.0.0.1)."),
    port: int | None = typer.Option(None, "--port", help="Bind port (default 8787)."),
    token: str | None = typer.Option(
        None, "--token", help="Require this bearer token on every request."
    ),
) -> None:
    """Start the local daemon exposing the engine over HTTP and WebSocket.

    Options override the environment (`AETHERIUS_DAEMON_HOST/PORT/TOKEN`). The daemon binds to
    loopback by default: it serves local processes only, never the network.
    """
    import uvicorn

    from ..server import DaemonConfig, create_app

    # Start from the environment (AETHERIUS_DAEMON_*), then let explicit CLI options win.
    config = DaemonConfig()
    if host is not None:
        config.host = host
    if port is not None:
        config.port = port
    if token is not None:
        config.token = token

    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


@app.command()
def record(
    name: str,
    url: str = typer.Option(..., "--url", help="Start URL for the demonstration."),
    act: str = typer.Option(
        "continuum", "--act", help="Recorder backend: 'continuum' (browser) or 'vector' (API)."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Directory for the recorded Blueprint (default ./blueprints)."
    ),
    no_secrets: bool = typer.Option(
        False,
        "--no-secrets",
        help="Keep username-like fields literal (passwords are always secrets).",
    ),
) -> None:
    """Record a Blueprint by demonstrating a task in a visible browser."""
    from rich.console import Console as RichConsole

    from ..core.errors import AetheriusError
    from ..recorder import record_blueprint

    rich_console = RichConsole()
    rich_console.print(f"[bold]Recording[/bold] {name!r} — a browser opens at {url}.")
    rich_console.print("Demonstrate the task, then close the window to finish.")

    def on_event(description: str) -> None:
        rich_console.print(f"  [dim]{description}[/dim]")

    try:
        path = record_blueprint(
            name,
            url,
            act=act,
            out_dir=out,
            on_event=on_event,
            credentials_as_secrets=not no_secrets,
        )
    except AetheriusError as exc:
        rich_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    rich_console.print(f"[bold green]Saved[/bold green] {path}")


@app.command(name="record-gestures")
def record_gestures_command(
    out: Path | None = typer.Option(
        None, "--out", help="Gesture library file to write (default: bundled human_library.json)."
    ),
) -> None:
    """Capture real mouse gestures to extend the stealth gesture library."""
    from rich.console import Console as RichConsole

    from ..core.errors import AetheriusError
    from ..recorder import record_gestures

    rich_console = RichConsole()
    rich_console.print("A browser opens. Move and click naturally, then close the window to save.")
    try:
        path, count = record_gestures(out_path=out)
    except AetheriusError as exc:
        rich_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    rich_console.print(f"[bold green]Added[/bold green] {count} gesture(s) to {path}")


def main(argv: list[str] | None = None) -> int:
    """Entry point used by the ``aetherius`` console script."""
    try:
        result = app(args=argv, standalone_mode=False)
    except typer.Abort:
        return 1
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
