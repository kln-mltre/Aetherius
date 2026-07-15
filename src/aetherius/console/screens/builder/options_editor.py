"""Editor for a Blueprint's durable options (debug, timeout, retries, stealth, session).

These are the options the README says belong in the Studio, not the per-run Debug toggle of the Runs
screen. ``collect`` returns only non-default keys (an empty dict when everything is default, so the
options block is omitted); ``load`` restores them when editing an existing file. An advanced inline
``stealth`` object is preserved verbatim, since the presets Select cannot represent it.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, Select, Switch

from ....stealth.policy import preset_names

_BACKOFFS = ("none", "linear", "exponential")


def _as_int(raw: str) -> Any:
    """Parse an int field: '' -> None (omit), a valid int -> int, anything else -> the raw string
    (kept so the preview's schema check flags it rather than silently dropping the mistake)."""
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return text


class OptionsEditor(Vertical):
    """Form for ``options`` with a shape matching the schema's options object."""

    DEFAULT_CSS = """
    OptionsEditor { height: auto; padding: 1 1 0 1; }
    OptionsEditor .opt-row { height: auto; padding: 0 0 1 0; }
    OptionsEditor Label { padding: 1 1 0 0; }
    OptionsEditor Input { width: 24; }
    """

    def __init__(self) -> None:
        super().__init__()
        # An inline stealth object (not a preset name) we cannot render in the Select; kept to avoid
        # dropping it on save when the user leaves the Select untouched.
        self._stealth_obj: dict[str, Any] | None = None
        # options.proxy (Jalon G) has no widget yet: preserve it verbatim so editing a proxy-bearing
        # Blueprint in the Studio never silently strips it. Edit the proxy in the JSON or via .env.
        self._proxy: Any = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="opt-row"):
            yield Switch(value=False, id="opt-debug")
            yield Label("Debug (visible browser + slow-mo)")
        with Horizontal(classes="opt-row"):
            yield Label("Timeout (ms)")
            yield Input(placeholder="30000", id="opt-timeout")
        with Horizontal(classes="opt-row"):
            yield Label("Retries max")
            yield Input(placeholder="0", id="opt-retries-max")
            yield Label("backoff")
            yield Select(
                [(b, b) for b in _BACKOFFS], value="none", allow_blank=False, id="opt-backoff"
            )
        with Horizontal(classes="opt-row"):
            yield Label("Stealth")
            yield Select(
                [(n, n) for n in preset_names()], value="off", allow_blank=False, id="opt-stealth"
            )
        with Horizontal(classes="opt-row"):
            yield Label("Session profile")
            yield Input(placeholder="my-profile", id="opt-session-profile")
            yield Switch(value=False, id="opt-session-persist")
            yield Label("persist")

    def collect(self) -> dict[str, Any]:
        """Read the widgets into an options dict, omitting anything left at its default."""
        options: dict[str, Any] = {}
        if self.query_one("#opt-debug", Switch).value:
            options["debug"] = True

        timeout = _as_int(self.query_one("#opt-timeout", Input).value)
        if timeout is not None:
            options["timeout_ms"] = timeout

        retries_max = _as_int(self.query_one("#opt-retries-max", Input).value)
        backoff = str(self.query_one("#opt-backoff", Select).value)
        if retries_max is not None and retries_max != 0:
            retries: dict[str, Any] = {"max": retries_max}
            if backoff != "none":
                retries["backoff"] = backoff
            options["retries"] = retries

        stealth = str(self.query_one("#opt-stealth", Select).value)
        if stealth != "off":
            options["stealth"] = stealth
        elif self._stealth_obj is not None:
            options["stealth"] = self._stealth_obj  # preserve an advanced inline config

        profile = self.query_one("#opt-session-profile", Input).value.strip()
        persist = self.query_one("#opt-session-persist", Switch).value
        if profile or persist:
            session: dict[str, Any] = {}
            if profile:
                session["profile"] = profile
            if persist:
                session["persist"] = True
            options["session"] = session

        if self._proxy is not None:
            options["proxy"] = self._proxy  # preserve verbatim (no widget yet)
        return options

    def load(self, options: dict[str, Any]) -> None:
        """Restore the widgets from an existing options dict (edit mode)."""
        self.query_one("#opt-debug", Switch).value = bool(options.get("debug", False))
        timeout = options.get("timeout_ms")
        self.query_one("#opt-timeout", Input).value = "" if timeout is None else str(timeout)

        retries = options.get("retries") or {}
        self.query_one("#opt-retries-max", Input).value = str(retries.get("max", "") or "")
        self.query_one("#opt-backoff", Select).value = retries.get("backoff", "none")

        stealth = options.get("stealth")
        if isinstance(stealth, dict):
            self._stealth_obj = stealth
            self.query_one("#opt-stealth", Select).value = "off"
        else:
            self._stealth_obj = None
            self.query_one("#opt-stealth", Select).value = (
                stealth if stealth in preset_names() else "off"
            )

        session = options.get("session") or {}
        self.query_one("#opt-session-profile", Input).value = str(session.get("profile", "") or "")
        self.query_one("#opt-session-persist", Switch).value = bool(session.get("persist", False))

        self._proxy = options.get("proxy")  # preserved verbatim across an edit/save round trip
