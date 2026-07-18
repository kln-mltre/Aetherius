"""Injected-JavaScript bridge and DOM extraction helpers for scraping.

Reads from the live page: ``extract`` turns a map of ``name -> {selector, as}`` into typed outputs,
``wait_for`` blocks until a selector appears (honouring a Blueprint failure code on timeout), and
``evaluate`` runs injected JavaScript. Like actions.py, these are pure ``(page, params, render)``
functions so they test against a fake page.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from ...core.errors import ActionError, StepTimeoutError

Renderer = Callable[[Any], Any]

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _is_timeout(exc: Exception) -> bool:
    """True when *exc* is a Playwright (or builtin) timeout, matched by class name.

    Avoids importing Playwright here so the module stays light and unit-testable.
    """
    return type(exc).__name__ == "TimeoutError"


def failure_code(on_timeout: Any) -> str | None:
    """Parse ``"fail:CODE"`` into ``CODE``; anything else yields no code.

    Public: the Oracle driver reuses it for the vision form of ``wait_for``.
    """
    if isinstance(on_timeout, str) and on_timeout.startswith("fail:"):
        return on_timeout.split(":", 1)[1] or None
    return None


def _resolve(page: Any, selector: str, selector_type: str) -> Any:
    if selector_type == "xpath":
        return page.locator(selector if selector.startswith("xpath=") else f"xpath={selector}")
    return page.locator(selector)


def _coerce_number(text: str | None) -> float | int | None:
    """Extract the first number from *text*, returning int when integral, else float."""
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    raw = match.group(0).replace(",", ".")
    value = float(raw)
    return int(value) if value.is_integer() else value


def _read_value(target: Any, as_: str, spec: Mapping[str, Any]) -> Any:
    """Read a single (already-resolved) locator as *as_*: text, number, html or attr."""
    if as_ == "text":
        return (target.inner_text() or "").strip()
    if as_ == "number":
        return _coerce_number(target.inner_text())
    if as_ == "html":
        return target.inner_html()
    if as_ == "attr":
        attr = spec.get("attr")
        if not attr:
            raise ActionError("extract 'as: attr' requires an 'attr' name.")
        return target.get_attribute(attr)
    raise ActionError(f"Unknown extract type {as_!r} (text, number, html, attr, list or count).")


def _read_one(page: Any, selector: str, as_: str, spec: Mapping[str, Any]) -> Any:
    selector_type = str(spec.get("selector_type", "css")).lower()
    locator = _resolve(page, selector, selector_type)
    if as_ == "count":
        return locator.count()
    return _read_value(locator.first, as_, spec)


def _read_list(page: Any, selector: str, spec: Mapping[str, Any]) -> list[Any]:
    """Read every match of *selector* as a list of values (item type via ``item``, default text)."""
    selector_type = str(spec.get("selector_type", "css")).lower()
    item_as = str(spec.get("item", "text")).lower()
    locator = _resolve(page, selector, selector_type)
    return [_read_value(target, item_as, spec) for target in locator.all()]


def _read_records(page: Any, spec: Mapping[str, Any], render: Renderer) -> list[dict[str, Any]]:
    """Read a repeating container into a list of records, one field per ``fields`` entry.

    Each field's selector is resolved *within* its container, so a row's ``.title``/``.price`` are
    read relative to that row rather than globally — the shape a table/list demonstration produces.
    """
    each = render(spec.get("each", ""))
    if not each:
        raise ActionError("extract records require an 'each' container selector.")
    fields: Mapping[str, Any] = spec.get("fields") or {}
    if not fields:
        raise ActionError("extract records require a non-empty 'fields' map.")

    records: list[dict[str, Any]] = []
    for container in page.locator(each).all():
        record: dict[str, Any] = {}
        for field_name, field_spec in fields.items():
            field_selector = render(field_spec.get("selector", ""))
            if not field_selector:
                raise ActionError(f"extract record field {field_name!r} requires a 'selector'.")
            field_as = str(render(field_spec.get("as", "text"))).lower()
            record[field_name] = _read_value(
                container.locator(field_selector).first, field_as, field_spec
            )
        records.append(record)
    return records


def extract(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    specs: Mapping[str, Any] = params.get("outputs") or {}
    result: dict[str, Any] = {}
    for name, spec in specs.items():
        if "each" in spec:
            result[name] = _read_records(page, spec, render)
            continue
        selector = render(spec.get("selector", ""))
        if not selector:
            raise ActionError(f"extract output {name!r} requires a 'selector'.")
        as_ = str(render(spec.get("as", "text"))).lower()
        if as_ == "list":
            result[name] = _read_list(page, selector, spec)
        else:
            result[name] = _read_one(page, selector, as_, spec)
    return result


def wait_for(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    selector = render(params.get("selector", ""))
    if not selector:
        raise ActionError("wait_for requires a 'selector'.")
    kwargs: dict[str, Any] = {"state": render(params.get("state", "visible"))}
    if params.get("timeout_ms") is not None:
        kwargs["timeout"] = float(render(params.get("timeout_ms")))
    try:
        # `.first`: waiting is about presence, so a selector matching several elements is normal
        # and must not trip Playwright's strict-mode (which is reserved for acting on one element).
        page.locator(selector).first.wait_for(**kwargs)
    except Exception as exc:
        if _is_timeout(exc):
            code = failure_code(render(params.get("on_timeout")))
            raise StepTimeoutError(
                f"wait_for timed out for selector {selector!r}", code=code
            ) from exc
        raise
    return {}


def evaluate(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    script = render(params.get("script", params.get("expression", "")))
    if not script:
        raise ActionError("evaluate requires a 'script' or 'expression'.")
    if "arg" in params:
        return {"result": page.evaluate(script, render(params.get("arg")))}
    return {"result": page.evaluate(script)}
