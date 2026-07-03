"""Command-line entry point.

Running ``aetherius`` with no argument opens the interactive Console (the terminal control center).
Subcommands (``run``, ``validate``, ``serve``, ``record``) are the scriptable, non-interactive paths.

Kept dependency-light on purpose: heavy imports (Textual for the Console, the Aetherius facade)
happen inside the relevant command, not at module import time.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, no_args_is_help=False)


def _parse_pairs(pairs: list[str], *, label: str) -> dict[str, str]:
    """Parse a list of ``key=value`` CLI options into a dict.

    Raises:
        typer.BadParameter: an entry has no ``=``.
    """
    result: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"Malformed {label} {pair!r}: expected key=value.")
        key, _, value = pair.partition("=")
        result[key] = value
    return result


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Dispatch to the Console when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        console()


@app.command()
def console() -> None:
    """Open the interactive terminal Console."""
    from .console.app import AetheriusConsoleApp

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

    from .core.blueprint.loader import load_blueprint
    from .core.errors import AetheriusError
    from .core.runtime.engine import RunEngine

    rich_console = RichConsole()
    inputs = _parse_pairs(input, label="--input")
    secrets = _parse_pairs(secret, label="--secret")

    try:
        loaded = load_blueprint(blueprint)
        if debug:
            loaded.options.debug = True
        result = RunEngine().run(loaded, inputs=inputs, secrets=secrets)
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

    from .core.blueprint.loader import load_blueprint
    from .core.blueprint.validator import validate_for_act
    from .core.errors import AetheriusError

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
def serve() -> None:
    """Start the local daemon (not implemented yet)."""
    typer.echo(
        "The daemon (`aetherius serve`) is not implemented yet. "
        "It is a pending milestone; see README.md 'État d'avancement'."
    )
    raise typer.Exit(1)


@app.command()
def record() -> None:
    """Launch the Blueprint recorder (not implemented yet)."""
    typer.echo(
        "The recorder (`aetherius record`) is not implemented yet. "
        "It is a pending milestone; see README.md 'État d'avancement'."
    )
    raise typer.Exit(1)


def main(argv: list[str] | None = None) -> int:
    """Entry point used by the ``aetherius`` console script."""
    try:
        result = app(args=argv, standalone_mode=False)
    except typer.Abort:
        return 1
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
