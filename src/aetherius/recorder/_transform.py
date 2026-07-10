"""Pure transformation of captured events into Blueprint steps, inputs, secrets and outputs.

No browser here: this is the testable heart of the recorder. Actions become navigate/click/fill/
select/press steps; overlay picks become a single coalesced ``extract`` step (single values, lists or
record tables) plus the Blueprint ``outputs`` map; ``wait_for`` and ``parameterize`` (turn a filled
value into an ``input``) round out the "beyond clicks" meta-actions.
"""

from __future__ import annotations

from typing import Any

from ._names import ident as _ident
from ._names import unique as _unique
from .capture import RecordedEvent
from .selector_synth import ElementDescriptor, SelectorChoice, synthesize

_CREDENTIAL_TOKENS = ("username", "user", "login", "email", "mail", "pass", "identifiant", "pseudo")
_CREDENTIAL_AUTOCOMPLETE = {"username", "email", "current-password", "new-password"}
# HTML input ``type`` -> Blueprint input spec. Dates stay ``string`` + ``format`` to match the
# convention in the shipped examples; a numeric field becomes a real ``number``. Anything else
# (text, tel, search, unknown) is a plain string.
_FIELD_TYPE_SPECS: dict[str, dict[str, Any]] = {
    "number": {"type": "number"},
    "range": {"type": "number"},
    "date": {"type": "string", "format": "date"},
    "datetime-local": {"type": "string", "format": "date-time"},
    "time": {"type": "string", "format": "time"},
    "email": {"type": "string", "format": "email"},
    "url": {"type": "string", "format": "uri"},
}
# A navigation right after one of these was triggered by it, not typed by hand.
_NAV_TRIGGERS = frozenset({"click", "press"})
_ELEMENT_KINDS = frozenset({"click", "fill", "select", "press"})
_EXTRACT_KINDS = frozenset({"extract", "extract_records"})


def _selector_fields(choice: SelectorChoice) -> dict[str, str]:
    """Selector fields for a step: ``selector_type`` omitted when it is the ``css`` default."""
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


def _choice(descriptor: ElementDescriptor | None) -> SelectorChoice:
    return synthesize(descriptor) if descriptor is not None else SelectorChoice("")


def _input_spec(descriptor: ElementDescriptor | None) -> dict[str, Any]:
    """Build an input spec from the picked field's HTML ``type``, defaulting to a required string."""
    field_type = (descriptor.field_type or "") if descriptor is not None else ""
    spec = dict(_FIELD_TYPE_SPECS.get(field_type, {"type": "string"}))
    spec["required"] = True
    return spec


class _Recording:
    """Accumulates the Blueprint pieces as captured events are handled, in order."""

    def __init__(self, *, credentials_as_secrets: bool) -> None:
        self.credentials_as_secrets = credentials_as_secrets
        self.steps: list[dict[str, Any]] = []
        self.secrets: list[str] = []
        self.inputs: dict[str, Any] = {}
        self.outputs: dict[str, Any] = {}
        self._secret_by_selector: dict[str, str] = {}
        self._extract: dict[str, Any] | None = None  # current open extract step
        self._extract_id: str = ""
        self._extract_seq = 0
        self._output_names: set[str] = set()
        self._prev_kind: str | None = None

    def handle(self, event: RecordedEvent) -> None:
        kind = event.kind
        if kind in _EXTRACT_KINDS:
            self._add_extraction(event)
        else:
            self._extract = None  # any non-extraction closes the coalesced extract step
            if kind == "navigate":
                self._add_navigate(event)
            elif kind == "wait_for":
                self._add_wait_for(event)
            elif kind == "parameterize":
                self._parameterize(event)
            elif kind in _ELEMENT_KINDS:
                self._add_element(event)
        self._prev_kind = kind

    # ── actions ──────────────────────────────────────────────────────────────
    def _add_navigate(self, event: RecordedEvent) -> None:
        if self._prev_kind not in _NAV_TRIGGERS and event.url:
            self.steps.append({"action": "navigate", "url": event.url})

    def _add_wait_for(self, event: RecordedEvent) -> None:
        choice = _choice(event.descriptor)
        config = event.config or {}
        # Presence check: a group class beats a positional path when there is no unique hook.
        if choice.strategy == "css_path" and config.get("group"):
            fields: dict[str, str] = {"selector": str(config["group"])}
        else:
            fields = _selector_fields(choice)
        self.steps.append({"action": "wait_for", **fields})

    def _add_element(self, event: RecordedEvent) -> None:
        choice = _choice(event.descriptor)
        selector_fields = _selector_fields(choice)
        if event.kind == "click":
            if event.url:  # a link click: navigate to its (stable) URL rather than replay the click
                self.steps.append({"action": "navigate", "url": event.url})
            else:
                self.steps.append({"action": "click", **selector_fields})
        elif event.kind == "press":
            self.steps.append({"action": "press", "key": event.key or "Enter", **selector_fields})
        elif event.kind == "select":
            self.steps.append({"action": "select", **selector_fields, "value": event.value or ""})
        elif event.kind == "fill":
            self._add_fill(event, choice, selector_fields)

    def _add_fill(
        self, event: RecordedEvent, choice: SelectorChoice, selector_fields: dict[str, str]
    ) -> None:
        secret = event.redacted or (
            self.credentials_as_secrets and _is_credential(event.descriptor)
        )
        if secret:
            value = f"{{{{ secrets.{self._secret_for(event, choice)} }}}}"
        else:
            value = event.value or ""
        step = {"action": "fill", **selector_fields, "value": value}
        last = self.steps[-1] if self.steps else None
        if (
            last is not None
            and last.get("action") == "fill"
            and last.get("selector") == choice.selector
        ):
            self.steps[-1] = step  # coalesce successive edits of the same field
        else:
            self.steps.append(step)

    def _secret_for(self, event: RecordedEvent, choice: SelectorChoice) -> str:
        name = self._secret_by_selector.get(choice.selector)
        if name is None:
            base = _ident(event.descriptor.name if event.descriptor else None, fallback="secret")
            name = _unique(base, set(self.secrets))
            self._secret_by_selector[choice.selector] = name
            self.secrets.append(name)
        return name

    def _parameterize(self, event: RecordedEvent) -> None:
        """Rewrite the most recent literal fill at this selector into an ``{{ inputs.x }}``."""
        selector = _choice(event.descriptor).selector
        for step in reversed(self.steps):
            if step.get("action") == "fill" and step.get("selector") == selector:
                if str(step.get("value", "")).startswith("{{ secrets."):
                    return  # a secret is not an input; leave it alone
                name = _unique(
                    _ident((event.config or {}).get("name"), fallback="value"), set(self.inputs)
                )
                step["value"] = f"{{{{ inputs.{name} }}}}"
                self.inputs[name] = _input_spec(event.descriptor)
                return

    # ── extraction ───────────────────────────────────────────────────────────
    def _add_extraction(self, event: RecordedEvent) -> None:
        if self._extract is None:
            self._extract_seq += 1
            self._extract_id = "data" if self._extract_seq == 1 else f"data_{self._extract_seq}"
            self._extract = {"action": "extract", "id": self._extract_id, "outputs": {}}
            self.steps.append(self._extract)
        config = event.config or {}
        name = _unique(_ident(config.get("name"), fallback="value"), self._output_names)
        self._output_names.add(name)
        self._extract["outputs"][name] = self._spec(event, config)
        self.outputs[name] = f"{{{{ steps.{self._extract_id}.{name} }}}}"

    def _spec(self, event: RecordedEvent, config: dict[str, Any]) -> dict[str, Any]:
        if event.kind == "extract_records":
            return self._records_spec(event, config)
        as_ = str(config.get("as", "text"))
        # list/count read *all* matches, so use the sibling-group selector; single values use the
        # unique selector our policy synthesizes from the descriptor.
        if as_ in ("list", "count") and config.get("group"):
            spec: dict[str, Any] = {"selector": str(config["group"])}
        else:
            spec = dict(_selector_fields(_choice(event.descriptor)))
        spec["as"] = as_
        if as_ == "list":
            item = str(config.get("item") or "text")
            if item != "text":
                spec["item"] = item
            if item == "attr" and config.get("attr"):
                spec["attr"] = str(config["attr"])
        elif as_ == "attr" and config.get("attr"):
            spec["attr"] = str(config["attr"])
        return spec

    def _records_spec(self, event: RecordedEvent, config: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        taken: set[str] = set()
        for raw in config.get("fields", []):
            fname = _unique(_ident(raw.get("name"), fallback="field"), taken)
            taken.add(fname)
            field_spec = {
                "selector": str(raw.get("selector", "")),
                "as": str(raw.get("as", "text")),
            }
            if raw.get("as") == "attr" and raw.get("attr"):
                field_spec["attr"] = str(raw["attr"])
            fields[fname] = field_spec
        each = str(config.get("each") or _choice(event.descriptor).selector)
        return {"each": each, "fields": fields}


def events_to_steps(
    events: list[RecordedEvent], *, credentials_as_secrets: bool = True
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any], dict[str, Any]]:
    """Transform captured events into ``(steps, secrets, inputs, outputs)``."""
    recording = _Recording(credentials_as_secrets=credentials_as_secrets)
    for event in events:
        recording.handle(event)
    return recording.steps, recording.secrets, recording.inputs, recording.outputs
