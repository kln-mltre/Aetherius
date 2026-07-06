"""Blueprint recorder: launch a visible browser, capture user actions, emit a clean minimal Blueprint.

The browser wiring lives in :mod:`.capture`; the transformation from captured events to a Blueprint
is pure and lives here, so it is unit-testable without a browser. The recorder emits an Act II
(Continuum) Blueprint: navigate/click/fill/select/press with robust selectors synthesized by
:mod:`.selector_synth`. Credentials (a password field, or a field that looks like a username/login)
become ``{{ secrets.x }}`` placeholders — a password value is never captured in the first place.

Every produced file is re-validated through the canonical loader/validator before it is returned, so
the recorder can only ever hand back a schema-valid, runnable Blueprint (or fail loudly).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from ..core.blueprint.loader import load_blueprint
from ..core.blueprint.validator import validate_for_act
from ..core.errors import BlueprintValidationError
from .capture import EventCallback, RecordedEvent, RecordingSession
from .selector_synth import ElementDescriptor, SelectorChoice, synthesize

# Tokens that mark a text field as a credential (matched against name/id/autocomplete).
_CREDENTIAL_TOKENS = ("username", "user", "login", "email", "mail", "pass", "identifiant", "pseudo")
_CREDENTIAL_AUTOCOMPLETE = {"username", "email", "current-password", "new-password"}
# Navigations that immediately follow one of these were plainly triggered by it, not typed by hand.
_NAV_TRIGGERS = frozenset({"click", "press"})
_ELEMENT_KINDS = frozenset({"click", "fill", "select", "press"})


def _selector_fields(choice: SelectorChoice) -> dict[str, str]:
    """Selector fields for a step: ``selector_type`` is omitted when it is the ``css`` default."""
    fields = {"selector": choice.selector}
    if choice.selector_type != "css":
        fields["selector_type"] = choice.selector_type
    return fields


def _is_credential(descriptor: ElementDescriptor | None) -> bool:
    """True when a text field looks like a credential worth turning into a secret."""
    if descriptor is None:
        return False
    if (descriptor.field_type or "") == "password":
        return True
    if (descriptor.autocomplete or "").lower() in _CREDENTIAL_AUTOCOMPLETE:
        return True
    haystack = f"{descriptor.name or ''} {descriptor.autocomplete or ''}".lower()
    return any(token in haystack for token in _CREDENTIAL_TOKENS)


def _slug(name: str) -> str:
    """Filesystem-safe stem derived from a Blueprint name (keeps dots, e.g. quotes.login)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return slug or "recording"


def _secret_name(descriptor: ElementDescriptor | None, taken: set[str]) -> str:
    """Derive a stable, unique secret variable name from the field's name (fallback: secret_N)."""
    raw = (descriptor.name or "") if descriptor is not None else ""
    base = re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_") or "secret"
    name = base
    counter = 2
    while name in taken:
        name = f"{base}_{counter}"
        counter += 1
    return name


def events_to_steps(
    events: list[RecordedEvent], *, credentials_as_secrets: bool = True
) -> tuple[list[dict[str, Any]], list[str]]:
    """Transform captured events into Blueprint steps and the list of secret names they introduce.

    Consecutive fills on the same target are coalesced to the last value; a navigation that merely
    followed a click/press is dropped (the click already implies it); credential fields become
    ``{{ secrets.x }}`` placeholders.
    """
    steps: list[dict[str, Any]] = []
    secrets: list[str] = []
    secret_by_selector: dict[str, str] = {}
    prev_kind: str | None = None

    for event in events:
        if event.kind == "navigate":
            if prev_kind not in _NAV_TRIGGERS and event.url:
                steps.append({"action": "navigate", "url": event.url})
        elif event.kind in _ELEMENT_KINDS:
            choice = synthesize(event.descriptor) if event.descriptor else SelectorChoice("")
            _append_element_step(
                steps,
                secrets,
                secret_by_selector,
                event,
                choice,
                credentials_as_secrets=credentials_as_secrets,
            )
        prev_kind = event.kind

    return steps, secrets


def _append_element_step(
    steps: list[dict[str, Any]],
    secrets: list[str],
    secret_by_selector: dict[str, str],
    event: RecordedEvent,
    choice: SelectorChoice,
    *,
    credentials_as_secrets: bool,
) -> None:
    """Build one element step (with coalescing for fills) and append it to *steps*."""
    selector_fields = _selector_fields(choice)
    if event.kind == "click":
        steps.append({"action": "click", **selector_fields})
    elif event.kind == "press":
        steps.append({"action": "press", "key": event.key or "Enter", **selector_fields})
    elif event.kind == "select":
        steps.append({"action": "select", **selector_fields, "value": event.value or ""})
    elif event.kind == "fill":
        is_secret = event.redacted or (credentials_as_secrets and _is_credential(event.descriptor))
        if is_secret:
            name = secret_by_selector.get(choice.selector)
            if name is None:
                name = _secret_name(event.descriptor, set(secrets))
                secret_by_selector[choice.selector] = name
                secrets.append(name)
            value = f"{{{{ secrets.{name} }}}}"
        else:
            value = event.value or ""
        step = {"action": "fill", **selector_fields, "value": value}
        last = steps[-1] if steps else None
        if (
            last is not None
            and last.get("action") == "fill"
            and last.get("selector") == choice.selector
        ):
            steps[-1] = step  # coalesce successive edits of the same field to the final value
        else:
            steps.append(step)


def assemble_blueprint(
    name: str, steps: list[dict[str, Any]], secrets: list[str], *, description: str | None = None
) -> dict[str, Any]:
    """Assemble a minimal, ordered Continuum Blueprint dict from the recorded steps."""
    blueprint: dict[str, Any] = {"aetherius": "1.0", "name": name}
    if description:
        blueprint["description"] = description
    blueprint["act"] = "continuum"
    if secrets:
        blueprint["secrets"] = secrets
    blueprint["steps"] = steps
    return blueprint


def describe_event(event: RecordedEvent) -> str:
    """Sober one-line description of a captured action, for CLI stdout and the Console event log."""
    if event.kind == "navigate":
        return f"navigate  {event.url or ''}"
    selector = synthesize(event.descriptor).selector if event.descriptor else "?"
    if event.kind == "press":
        return f"press {event.key or 'Enter'}  {selector}"
    return f"{event.kind}  {selector}"


def record_blueprint(
    name: str,
    start_url: str,
    *,
    out_dir: Path | str | None = None,
    on_event: EventCallback | None = None,
    stop_event: threading.Event | None = None,
    credentials_as_secrets: bool = True,
) -> Path:
    """Record a demonstration in a live browser and write a clean, validated Blueprint file.

    Returns the path of the written ``.blueprint.json`` (under *out_dir* or ``./blueprints/``).
    Raises :class:`BlueprintValidationError` if the assembled Blueprint fails canonical validation.
    """
    session = RecordingSession(start_url, on_event=on_event, stop_event=stop_event)
    events = session.record()
    steps, secrets = events_to_steps(events, credentials_as_secrets=credentials_as_secrets)
    description = f"Act II (Continuum) : genere par le recorder depuis une demo sur {start_url}."
    blueprint = assemble_blueprint(name, steps, secrets, description=description)

    target_dir = Path(out_dir) if out_dir is not None else Path.cwd() / "blueprints"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{_slug(name)}.blueprint.json"
    path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        validate_for_act(load_blueprint(path))
    except Exception as exc:  # a produced-invalid Blueprint is our bug: surface it, do not hide it
        raise BlueprintValidationError(
            f"The recorder produced an invalid Blueprint: {exc}"
        ) from exc
    return path
